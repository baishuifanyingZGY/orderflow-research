"""Generate publication figures, an HTML report, Markdown, and a PDF from results.

This module never fits models or selects parameters. All claims derive from
the frozen research outputs. Analytical outputs: CC BY-NC-SA 4.0.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

NAMES = {"zero":"Zero forecast", "ridge_control":"Price controls", "ridge_quote_only":"Quotes only", "ridge_orderflow":"+ Trade flow", "ridge_liquidity":"+ Liquidity interactions", "hist_gradient_boosting":"Boosted trees"}
NAVY, TEAL, ORANGE, GRAY = "#142b45", "#007f83", "#df7837", "#65758a"


def fnum(value, digits=4):
    return "n/a" if pd.isna(value) else f"{value:,.{digits}f}"


def build_report(root: str | Path):
    root = Path(root)
    results, docs = root / "results", root / "docs"
    figures = docs / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    s = json.loads((results / "summary.json").read_text())
    manifest = json.loads((root / "data/audit/manifest.json").read_text())
    metrics = pd.read_csv(results / "model_metrics.csv")
    test = metrics.loc[metrics.split.eq("test")].set_index("model")
    val = metrics.loc[metrics.split.eq("validation")].set_index("model")
    best = s["selection"]["selected_model"]
    selected = test.loc[best]
    costs = pd.read_csv(results / "cost_sensitivity.csv")
    all_costs = costs.loc[costs.symbol.eq("ALL")]
    economic = all_costs.loc[(all_costs.entry_delay_seconds == 1) & (all_costs.fee_bps_per_side == 1)]
    cost_value = float(economic.iloc[0].mean_net_bps) if len(economic) else None
    quote_rows = sum(x["book_rows"] for x in manifest)
    trade_rows = sum(x["trade_rows"] for x in manifest)
    plt.rcParams.update({"font.family":"DejaVu Sans", "font.size":10, "axes.spines.top":False,
        "axes.spines.right":False, "axes.labelcolor":NAVY, "text.color":NAVY,
        "axes.edgecolor":"#c4ccd5", "xtick.color":GRAY, "ytick.color":GRAY,
        "figure.facecolor":"white", "axes.facecolor":"white", "savefig.dpi":180})

    def save(fig, name):
        fig.tight_layout(pad=1.7)
        fig.savefig(figures / f"{name}.png", bbox_inches="tight")
        fig.savefig(figures / f"{name}.svg", bbox_inches="tight")
        svg = figures / f"{name}.svg"
        svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
        plt.close(fig)

    audit = pd.DataFrame(manifest)
    volume = audit.pivot(index="date", columns="symbol", values="book_rows") / 1e6
    fig, ax = plt.subplots(figsize=(10,3.5))
    volume.plot.bar(ax=ax, color=[NAVY,TEAL], width=.8)
    ax.set_xticklabels([d[5:] for d in volume.index],rotation=45)
    ax.axvline(6.5,color=ORANGE,ls="--",lw=1); ax.axvline(9.5,color=ORANGE,ls="--",lw=1)
    ax.set(xlabel="UTC date in January 2024 | train 01-07, validation 08-10, test 11-14",ylabel="Observed quote updates (millions)")
    ax.legend(title=None,frameon=False)
    save(fig,"data_coverage")

    fig, ax=plt.subplots(figsize=(10,3.8))
    vals=test.r2_vs_zero*100
    ax.barh([NAMES[n]+(" *" if n==best else "") for n in test.index],vals,
            color=[TEAL if n==best else "#8194aa" for n in test.index])
    ax.axvline(0,color=NAVY,lw=.8)
    ax.set_xlabel("Test R² versus zero forecast (%) | * validation-selected model")
    ax.invert_yaxis()
    save(fig,"model_comparison")

    calibration=pd.read_csv(results/"calibration.csv")
    fig,ax=plt.subplots(figsize=(6.5,3.7))
    ax.plot(calibration.predicted_bps,calibration.realized_1s_bps,"o-",color=TEAL,label="Test bin means")
    lo=min(calibration.predicted_bps.min(),calibration.realized_1s_bps.min())
    hi=max(calibration.predicted_bps.max(),calibration.realized_1s_bps.max())
    ax.plot([lo,hi],[lo,hi],"--",color=GRAY,label="Perfect calibration")
    ax.axhline(0,color="#d8dee4",lw=.7);ax.axvline(0,color="#d8dee4",lw=.7)
    ax.set(xlabel="Mean frozen forecast (bps)",ylabel="Mean next-second return (bps)")
    ax.legend(frameon=False)
    save(fig,"calibration")

    h=pd.read_csv(results/"horizon_metrics.csv")
    fig,ax=plt.subplots(figsize=(6.5,3.7))
    for symbol,color in [("ALL",NAVY),("BTCUSDT",TEAL),("ETHUSDT",ORANGE)]:
        g=h[h.symbol.eq(symbol)]
        ax.plot(g.horizon_seconds,g.correlation,"o-",label=symbol,color=color)
    ax.set(xlabel="Future midpoint horizon (seconds)",ylabel="Correlation with frozen 1-second forecast",xticks=[1,5,10])
    ax.axhline(0,color=GRAY,lw=.7);ax.legend(frameon=False)
    save(fig,"signal_horizon")

    fig,ax=plt.subplots(figsize=(7,3.5))
    if len(all_costs):
        matrix=all_costs.pivot(index="fee_bps_per_side",columns="entry_delay_seconds",values="mean_net_bps")
        im=ax.imshow(matrix.to_numpy(),cmap="RdYlBu",aspect="auto")
        for i in range(len(matrix)):
            for j in range(len(matrix.columns)):
                rgba=im.cmap(im.norm(matrix.iloc[i,j]))
                luminance=.2126*rgba[0]+.7152*rgba[1]+.0722*rgba[2]
                ax.text(j,i,f"{matrix.iloc[i,j]:.3f}",ha="center",va="center",color="white" if luminance<.48 else NAVY,fontweight="bold")
        ax.set(xticks=range(len(matrix.columns)),xticklabels=matrix.columns,yticks=range(len(matrix)),yticklabels=matrix.index,
               xlabel="Assumed entry delay (seconds)",ylabel="Assumed fee (bps per side)")
        fig.colorbar(im,ax=ax,label="Mean hypothetical round-trip return (bps)")
    else:
        ax.text(.5,.5,"No qualifying decisions",ha="center",va="center")
    save(fig,"cost_sensitivity")

    daily=s["bootstrap"]["daily_improvements"]
    fig,ax=plt.subplots(figsize=(7,3.4))
    ax.bar([x[5:] for x in daily],list(daily.values()),color=[TEAL if v>=0 else ORANGE for v in daily.values()])
    ax.axhline(0,color=NAVY,lw=.8)
    ax.set(xlabel="UTC test date in January 2024",ylabel="Control MSE minus selected MSE (bps²)")
    save(fig,"daily_improvement")

    mark=pd.read_csv(results/"markout_proxy.csv")
    fig,ax=plt.subplots(figsize=(7,3.4))
    for flow,color,label in [("buy",ORANGE,"Ask-side proxy after buy flow"),("sell",TEAL,"Bid-side proxy after sell flow")]:
        g=mark[mark.recent_trade_flow.eq(flow)]
        ax.plot(g.horizon_seconds,g.hypothetical_quote_side_markout_bps,"o-",color=color,label=label)
    ax.set(xlabel="Future midpoint horizon (seconds)",ylabel="Hypothetical quote-side markout (bps)",xticks=[1,5,10])
    ax.axhline(0,color=GRAY,lw=.7);ax.legend(frameon=False,fontsize=9)
    save(fig,"markout_proxy")

    ci=s["bootstrap"]["percentile_95_ci_bps_squared"]
    improvement=1-float(selected.mse)/float(test.loc["ridge_control","mse"])
    result_sentence=(f"{NAMES[best]} was selected using validation MSE. On the four-day test, its R² relative to a zero-return forecast was {selected.r2_vs_zero*100:.3f}%, and its MSE was {abs(improvement)*100:.3f}% {'lower' if improvement>=0 else 'higher'} than the price-control Ridge model.")
    cost_sentence=(f"At a one-second assumed entry delay and one basis point of fees per side, the mean hypothetical five-second round trip was {cost_value:.4f} bps across {int(economic.iloc[0]['n']):,} eligible decisions." if cost_value is not None else "The frozen decision rule produced no eligible hypothetical trades.")
    raw_gb=sum(z["bytes"] for x in manifest for z in x["sources"])/1e9
    table=[[NAMES[n]+(" *" if n==best else ""),fnum(val.loc[n,"mse"]),fnum(test.loc[n,"mse"]),fnum(test.loc[n,"r2_vs_zero"]*100,3)+"%"] for n in test.index]
    sections=[
      {"title":"Question and evidence", "paragraphs":[
        "Does observed top-of-book order flow improve forecasts of future midpoint changes, and do liquidity conditions change that value? This study separates prediction from contemporaneous price impact and from hypothetical execution economics.",
        result_sentence,cost_sentence,
        "The evidence is restricted to BTCUSDT and ETHUSDT perpetual futures on one venue, January 1-14, 2024. Four test days are insufficient to establish persistent alpha. This independent, AI-assisted project has no affiliation with Citadel Securities, MIT or the data provider."]},
      {"title":"Data and provenance", "paragraphs":[
        f"The pipeline processed {quote_rows:,} BBO updates and {trade_rows:,} aggregate trade records from 56 vendor-checksummed daily archives ({raw_gb:.2f} GB compressed). Data expenditure was $0 against a $100 cap. Raw and per-second datasets remain outside Git; source URLs, checksums and processing audits are committed.",
        "A substantive quality issue was discovered before model fitting: BTCUSDT January 2 interleaves early-day and late-day records. The loader now stops on disorder, performs disk-backed sorting by event time and update ID, and then aggregates the complete chronological stream. No date was removed. The repair and original intermediate files are documented.",
        "All decisions use a one-second UTC grid. Quote event time is an exchange publication proxy, not local receive time. Trade availability is assumed to be transaction time plus 1,000 ms. Quotes published more than one second ago are excluded at endpoints. All observed BBO transitions contribute to OFI before downsampling; archive event completeness is unverified.",
        "Fresh publication does not guarantee fresh market state. Source audits find publication backlogs as large as 128 seconds in training and a sampled BTC 99th-percentile delay of 5.32 seconds on January 9. Published backlogged states remain eligible. Forecasts may partly capture feed catch-up, and the assumed trade delay does not resolve this timing mismatch."],"figure":"data_coverage","caption":"Daily input coverage. Dashed separators show the fixed chronological partitions."},
      {"title":"Research design", "paragraphs":[
        "Train: January 1-7; validation: January 8-10; test: January 11-14. Training uses every fifth second; validation and test retain every eligible second. Daily features reset with a 60-second warmup. Labels never cross UTC-day boundaries. Median imputation, scaling and regime boundaries use training data only.",
        "The primary target is the next-second midpoint simple return in basis points. The feature families are past returns, spread and volatility; queue imbalance and observed best-quote OFI; lagged signed-trade imbalance and event intensity; log depth and flow/liquidity interactions. Quote-only ablation isolates dependence on trade timing.",
        "Six candidates were fixed before evaluation: zero, price-control Ridge, quote-only Ridge, full-flow Ridge, liquidity-interaction Ridge, and a small histogram gradient boosting model. Ridge alpha is 100. The tree uses 100 iterations, depth 3, 15 maximum leaves, learning rate 0.05 and L2 penalty 10; no random validation or early stopping. The lowest validation-MSE model is retained without refitting.",
        f"Retained samples: {s['sample_sizes']['train_sampled']:,} training anchors, {s['sample_sizes']['validation']:,} validation anchors, and {s['sample_sizes']['test']:,} test anchors. The zero-relative R² is 1 - model MSE / mean(target²); it is not the centered R² used by many libraries."]},
      {"title":"Forecast results", "paragraphs":[result_sentence,
        "The selected model is marked with an asterisk. Other test model comparisons are diagnostic; the test set was not used to choose a model or horizon. All candidates, including failures, are reported.",
        "Quote-only Ridge already captures much of the incremental predictive information. Adding trade features gives a smaller improvement. Liquidity-interaction Ridge performs worse than full-flow Ridge on validation but slightly better on test, so a consistent benefit from those interactions is not established by this sample."],
       "figure":"model_comparison","caption":"One-second test performance. Negative R² indicates worse error than a zero forecast.",
       "table":{"headers":["Model","Validation MSE","Test MSE","Test R²"],"rows":table}},
      {"title":"Calibration, horizon and stability", "paragraphs":[
        "Prediction bins use validation-derived boundaries; their test realized returns show whether forecast magnitudes transfer. The horizon diagnostic compares the same frozen one-second forecast to 1-, 5- and 10-second returns; it does not retrain a model for each horizon.",
        f"The equal-day mean improvement over price controls is {s['bootstrap']['mean_improvement_bps_squared']:.6f} bps². A descriptive 5,000-resample day-cluster interval is [{ci[0]:.6f}, {ci[1]:.6f}] bps². BTC and ETH are resampled together by UTC day. With only four independent day clusters, this interval does not establish statistical significance or long-run stability."],
       "figure":"calibration","caption":"Calibration of the validation-selected model on test observations.",
       "second_figure":"signal_horizon","second_caption":"Correlation across horizons, using the unchanged one-second forecast."},
      {"title":"Cost and adverse-selection diagnostics", "paragraphs":[cost_sentence,
        "Decisions occur on a fixed ten-second grid when the absolute forecast exceeds its validation 90th percentile. A long crosses the ask on entry and bid on exit; a short crosses the bid then ask. Delays are 0, 1 or 2 seconds; holding time is five seconds. Fees of 0, 1 or 5 bps per side are scenarios, not historical account fee claims. Each symbol's scenarios have nonoverlapping positions.",
        "These are negligible-size, complete-case calculations conditional on valid future labels and exit quotes. Missing future outcomes are excluded. Extra slippage, impact, receive-time latency, funding, margin and inventory financing are omitted. These are not an ex-ante executable strategy, live fills or realized P&L.",
        "The separate quote-side markout proxy conditions a hypothetical bid or ask execution on recent signed trade flow. It illustrates exposure to subsequent price movement; it is not measured at actual executions and cannot establish fill probability or realized maker returns."],
       "figure":"cost_sensitivity","caption":"Mean hypothetical return, after crossing both sides of the spread and charging both fees.",
       "second_figure":"markout_proxy","second_caption":"Hypothetical quote-side endpoint markouts; no passive fills are assumed or verified."},
      {"title":"What the experiment can support", "paragraphs":[
        "This project demonstrates a complete research chain: source validation, chronological event reconstruction, causal feature construction, nested baselines, model selection on validation only, a sealed test, and economic diagnostics. A negative net scenario is an informative result, not a reason to hide the experiment.",
        "The principal limits are the short historical window, two correlated instruments, a single venue, base-asset depth units that differ across symbols, and assumed publication timing for trades. Top-of-book updates do not reveal the complete order book, hidden liquidity, queue priority or cancellation intentions. Results do not transfer automatically to US equities or present-day markets.",
        "The next study should add more independent dates and market regimes, validate on a separate venue or licensed equity dataset, and improve receive-time and execution modeling. The $100 budget remains unspent; a paid upgrade should be scoped by a vendor's concrete quote and publication rights."],
       "figure":"daily_improvement","caption":"All four test-day outcomes, clustered jointly across BTC and ETH. Positive means lower error than price controls."},
      {"title":"Reproduction and references", "paragraphs":[
        "Install Python 3.11+ dependencies with python -m pip install -e '.[dev]'. Run python run.py data, python run.py research, and python run.py report. The data command downloads about 6 GB; derived storage and temporary sorting need additional space. Unit tests run with python -m pytest -q. See README for a fresh-output reproduction workflow; completed test results are protected against accidental overwrite.",
        "The code, configuration, SHA-256 manifests, data audit, preprocessing statistics, model coefficients, daily metrics and result tables are included. The report is generated from results/summary.json and CSV tables without refitting. Generated forecast rows and raw inputs are intentionally not committed.",
        "Sources: Cont, Kukanov & Stoikov, The Price Impact of Order Book Events (arxiv.org/abs/1011.6402); Gould & Bonart, Queue Imbalance as a One-Tick-Ahead Price Predictor (arxiv.org/abs/1512.03492); Binance public-data repository and Vision Dataset Terms, version 1.0, August 26, 2026 (github.com/binance/binance-public-data).",
        "Attribution: historical data provided by Binance Vision. Analytical reports, charts and derived outputs are distributed under CC BY-NC-SA 4.0 and the applicable dataset terms. Independently authored software is MIT licensed. The implementation and documentation were produced with AI assistance; no employment, institutional affiliation or third-party endorsement is implied."]}
    ]
    _write_html(docs/"report.html",sections,s,result_sentence,cost_value)
    _write_markdown(docs/"report.md",sections)
    _write_pdf(root/"output/pdf/orderflow-research.pdf",sections,figures)
    (results/"presentation_facts.json").write_text(json.dumps({"selected_model":best,"quote_rows":quote_rows,"aggregate_trade_rows":trade_rows,"test_r2_vs_zero":float(selected.r2_vs_zero),"mse_improvement_vs_control":improvement,"cost_1s_delay_1bp_per_side":cost_value,"result_sentence":result_sentence,"cost_sentence":cost_sentence},indent=2)+"\n")
    print(f"Report generated: {docs/'report.html'}",flush=True)


def _write_markdown(path,sections):
    out=["# When does order flow predict prices?\n", "BTC & ETH perpetual futures | January 1-14, 2024\n"]
    for section in sections:
        out.append("## "+section["title"]+"\n")
        out.extend(p+"\n" for p in section["paragraphs"])
        if "table" in section:
            t=section["table"]
            out += ["| "+" | ".join(t["headers"])+" |", "| "+" | ".join(["---"]*len(t["headers"]))+" |"]
            out.extend("| "+" | ".join(row)+" |" for row in t["rows"])
        for key,cap in [("figure","caption"),("second_figure","second_caption")]:
            if key in section: out += [f"\n![{section[cap]}](figures/{section[key]}.png)\n",section[cap]+"\n"]
    path.write_text("\n".join(out))


def _write_html(path,sections,s,headline,cost):
    blocks=[]
    for i,section in enumerate(sections):
        body="".join(f"<p>{html.escape(p)}</p>" for p in section["paragraphs"])
        if "table" in section:
            t=section["table"]
            body+="<div class='table-wrap'><table><thead><tr>"+"".join(f"<th>{html.escape(x)}</th>" for x in t["headers"])+"</tr></thead><tbody>"
            body+="".join("<tr>"+"".join(f"<td>{html.escape(x)}</td>" for x in row)+"</tr>" for row in t["rows"])+"</tbody></table></div>"
        for key,cap in [("figure","caption"),("second_figure","second_caption")]:
            if key in section: body+=f"<figure><img src='figures/{section[key]}.svg' alt='{html.escape(section[cap])}'><figcaption>{html.escape(section[cap])}</figcaption></figure>"
        blocks.append(f"<section id='s{i}'><div class='number'>{i+1:02d} / RESEARCH</div><h2>{html.escape(section['title'])}</h2>{body}</section>")
    title="When does order flow<br>predict prices?"
    document="""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Order Flow Research</title><style>
    :root{--navy:#142b45;--teal:#007f83;--muted:#617186}*{box-sizing:border-box}body{margin:0;background:#f2f5f7;color:var(--navy);font:16px/1.75 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}header{background:var(--navy);color:#fff;padding:64px max(6vw,24px) 44px}header .inner,main{max-width:1080px;margin:auto}.eyebrow,.number{font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase}.eyebrow{color:#72d1d1}h1{font-size:clamp(34px,5vw,62px);line-height:1.1;letter-spacing:-2px;margin:22px 0}header p{color:#d0dbe6;max-width:740px}.tags{display:flex;gap:9px;flex-wrap:wrap}.tags span{border:1px solid #547086;border-radius:30px;padding:5px 12px;font-size:12px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:32px}.card{border-top:2px solid #72d1d1;padding-top:13px}.card b{display:block;font-size:28px;line-height:1.4}.card small{color:#c0d0df}main{padding:26px 24px 70px}section{background:white;padding:38px 42px;margin:22px 0;border:1px solid #e0e6eb;border-radius:12px}.number{color:var(--teal)}h2{font-size:29px;line-height:1.3;margin:12px 0 20px}p{margin:0 0 16px}figure{margin:25px 0 0}img{display:block;width:100%;height:auto}figcaption{font-size:12px;color:var(--muted);margin-top:10px;border-left:2px solid #abc;padding-left:12px}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;margin:24px 0}th,td{text-align:left;padding:11px 12px;border-bottom:1px solid #e4e9ed}th{background:#eaf1f5}footer{font-size:12px;color:var(--muted);padding:20px 24px;max-width:1080px;margin:auto}a{color:var(--teal)}@media(max-width:600px){section{padding:25px 20px}.cards{grid-template-columns:1fr}h1{letter-spacing:-1px}}@media print{header{padding:25px}section{break-inside:avoid;border:0}body{background:white}main{padding:0}}
    </style></head><body>"""
    selected=next(m for m in s["metrics"] if m["split"]=="test" and m["model"]==s["selection"]["selected_model"])
    document+=f"<header><div class='inner'><div class='eyebrow'>Independent quantitative research / 2024 historical sample</div><h1>{title}</h1><p>Liquidity, signal persistence and the cost of acting on a forecast.<br>BTCUSDT &amp; ETHUSDT perpetual futures · January 1–14, 2024</p><div class='tags'><span>Real exchange archives</span><span>Chronological holdout</span><span>AI-assisted implementation</span><span>Data cost $0 / $100 cap</span></div><div class='cards'><div class='card'><b>{selected['r2_vs_zero']*100:.3f}%</b><small>Selected-model test R² vs zero</small></div><div class='card'><b>{fnum(cost,3)} bps</b><small>Hypothetical return / 1s delay / 1bp each side</small></div><div class='card'><b>4 days</b><small>Independent test-time clusters</small></div></div></div></header><main>"+"".join(blocks)+"</main><footer>Data: Binance Vision. Derived analytical outputs: CC BY-NC-SA 4.0. Code: MIT.<br><a href='https://github.com/baishuifanyingZGY/orderflow-research'>Repository</a> · <a href='../output/pdf/orderflow-research.pdf'>PDF report</a> · <a href='research_protocol.md'>Research protocol</a></footer></body></html>"
    path.write_text(document)


def _write_pdf(path,sections,figures):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    path.parent.mkdir(parents=True,exist_ok=True)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportBody",fontName="Helvetica",fontSize=9.5,leading=14,textColor=colors.HexColor(NAVY),spaceAfter=10))
    styles.add(ParagraphStyle(name="ReportTitle",fontName="Helvetica-Bold",fontSize=28,leading=32,textColor=colors.HexColor(NAVY),spaceAfter=18))
    styles.add(ParagraphStyle(name="ReportHeading",fontName="Helvetica-Bold",fontSize=19,leading=23,textColor=colors.HexColor(NAVY),spaceAfter=16))
    styles.add(ParagraphStyle(name="ReportCaption",fontName="Helvetica",fontSize=8,leading=11,textColor=colors.HexColor(GRAY),spaceAfter=14))
    story=[]
    def para(text,style="ReportBody"):
        text=text.replace("²","<super>2</super>").replace("–","-").replace("×","x")
        return Paragraph(text,styles[style])
    for i,section in enumerate(sections):
        if i: story.append(PageBreak())
        story.append(para(f"{i+1:02d} / ORDER-FLOW RESEARCH","ReportCaption"))
        if i==0:
            story.append(Spacer(1,36))
            story.append(para("When does order flow<br/>predict prices?","ReportTitle"))
            story.append(para("Liquidity, signal persistence and execution costs<br/>BTC &amp; ETH perpetual futures | January 1-14, 2024","ReportCaption"))
        else: story.append(para(section["title"],"ReportHeading"))
        for p in section["paragraphs"]: story.append(para(html.escape(p)))
        if "table" in section:
            t=section["table"]
            rows=[[para(html.escape(str(x)),"ReportCaption") for x in row] for row in [t["headers"]]+t["rows"]]
            table=Table(rows,colWidths=[179,95,95,100],repeatRows=1)
            table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eaf1f5")),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),1),("LINEBELOW",(0,0),(-1,-1),.4,colors.HexColor("#d7e0e7"))]))
            story.extend([table,Spacer(1,12)])
        for key,cap in [("figure","caption"),("second_figure","second_caption")]:
            if key in section:
                from PIL import Image as PILImage
                p=figures/f"{section[key]}.png"
                width,height=PILImage.open(p).size
                display_width=469
                if "second_figure" in section: display_width=385
                story.append(Image(str(p),width=display_width,height=display_width*height/width))
                story.append(para(html.escape(section[cap]),"ReportCaption"))
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor("#d7e0e7"));canvas.line(56,43,A4[0]-56,43)
        canvas.setFont("Helvetica",7);canvas.setFillColor(colors.HexColor(GRAY))
        canvas.drawString(56,30,"Independent research | Binance Vision data | Analytical outputs: CC BY-NC-SA 4.0")
        canvas.drawRightString(A4[0]-56,30,str(doc.page))
    SimpleDocTemplate(str(path),pagesize=A4,rightMargin=56,leftMargin=56,topMargin=46,bottomMargin=57,
                      title="When does order flow predict prices?",author="Independent research, AI-assisted").build(story,onFirstPage=footer,onLaterPages=footer)
