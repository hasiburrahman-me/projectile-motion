// Builds concept_note.docx (A4, Times New Roman, black). Run: node build_concept_note.js
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  AlignmentType, WidthType, BorderStyle, ShadingType, LevelFormat, HeadingLevel,
  Footer, PageNumber,
} = require("docx");

const FONT = "Times New Roman";
const SIZE = 22; // 11 pt

// Inline markup: **bold**, *italic*, [[placeholder]] (highlighted yellow), _{sub}
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|\[\[[^\]]+\]\]|_\{[^}]+\})/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("[[")) out.push(new TextRun({ text: "[" + t.slice(2, -2) + "]", highlight: "yellow", ...base }));
    else if (t.startsWith("_{")) out.push(new TextRun({ text: t.slice(2, -1), subScript: true, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}

const para = (text, opts = {}) =>
  new Paragraph({ children: runs(text), spacing: { after: 100 }, alignment: AlignmentType.JUSTIFIED, ...opts });
const heading = (text) =>
  new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)], spacing: { before: 160, after: 80 } });
const bullet = (text) =>
  new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: runs(text), spacing: { after: 50 }, alignment: AlignmentType.JUSTIFIED });
const numbered = (ref, text) =>
  new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(text), spacing: { after: 50 }, alignment: AlignmentType.JUSTIFIED });

const border = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
const borders = { top: border, bottom: border, left: border, right: border };
function table(widths, rows) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((cells, r) => new TableRow({
      tableHeader: r === 0,
      children: cells.map((c, i) => new TableCell({
        borders,
        width: { size: widths[i], type: WidthType.DXA },
        shading: r === 0 ? { fill: "E6E6E6", type: ShadingType.CLEAR, color: "auto" } : undefined,
        margins: { top: 40, bottom: 40, left: 80, right: 80 },
        children: [new Paragraph({ children: runs(c, { size: 19, bold: r === 0 ? true : undefined }) })],
      })),
    })),
  });
}
const caption = (text) =>
  new Paragraph({ children: runs(text, { size: 19, italics: true }), alignment: AlignmentType.CENTER, spacing: { before: 60, after: 140 } });

// A4 with 2.2 cm margins -> text width 9,474 DXA
const TW = 9474;

const body = [
  new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { after: 60 },
    children: [new TextRun({ text: "Physics-Informed, Uncertainty-Aware Short-Term Wind Power Forecasting", bold: true, size: 30 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { after: 40 },
    children: [new TextRun({ text: "Concept note for a joint journal paper", italics: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { after: 200 },
    children: runs("Prepared by Hasibur Rahman for Dr [[supervisor's full name]] Hossain  ·  October 2026"),
  }),

  heading("1. Research problem"),
  para("Wind power is variable, so grid and wind-farm operators rely on short-term forecasts (10 minutes to 6 hours ahead) for reserve scheduling, market bidding and balancing. Deep learning models such as CNN–GRU give strong point accuracy on these horizons [1, 2]. Two weaknesses still limit operational trust:"),
  numbered("prob", "**Physically implausible forecasts.** A data-driven model can predict power above rated capacity, power when the wind is below cut-in speed, power far from the turbine's power curve, or ramps faster than the farm can follow. Constraint-aware training has added capacity and ramp penalties to the loss [1], but the turbine's power-curve behaviour is not yet enforced."),
  numbered("prob", "**No reliable uncertainty.** Most forecasters output a single value. Where prediction intervals are produced, their stated coverage is often not achieved in practice, so operators cannot size reserves from them."),
  para("This paper aims to make the forecaster both **physics-consistent** and **uncertainty-aware**, without losing point accuracy."),

  heading("2. Research gap"),
  para("Existing work covers parts of the problem but not all of it together. Deep forecasters ignore turbine physics; probabilistic forecasters rarely check calibration or physical feasibility; and constraint-aware forecasters handle capacity and ramp limits, but not the power curve or uncertainty."),
  table([2050, 1500, 1750, 1650, 2524], [
    ["Work", "Model", "Physics in loss", "Uncertainty", "How this paper differs"],
    ["Hossain et al., 2025 [1]", "CNN–GRU", "Capacity, ramp", "None (point)", "Adds power-curve physics and calibrated intervals"],
    ["Hossain et al., 2024 [2]", "[[to fill]]", "[[to fill]]", "[[to fill]]", "[[to fill]]"],
    ["[[EAAI 2025 paper]] [3]", "[[to fill]]", "[[to fill]]", "[[to fill]]", "[[to fill]]"],
    ["Physics-informed neural networks [4, 5]", "MLP", "PDE residuals", "None", "Uses turbine operating rules instead of a PDE"],
    ["Conformalized quantile regression [6]", "Any", "None", "Calibrated intervals", "Adds physical bounds and wind-regime calibration"],
  ]),
  para("**Gap:** to our knowledge, no wind power forecaster combines power-curve-consistent training with conformally calibrated, physically bounded prediction intervals.", { spacing: { before: 100, after: 100 }, alignment: AlignmentType.JUSTIFIED }),

  heading("3. Novelty"),
  bullet("**Power-curve physics in the loss, with joint wind–power forecasting.** A tolerance band around the measured farm power curve, plus cut-in, rated and cut-out rules, is added to the capacity and ramp penalties of [1]. Because future wind speed is unknown at forecast time, the model also forecasts wind speed, and the loss penalises any mismatch between forecast power and the power curve of forecast wind speed."),
  bullet("**Physically bounded, calibrated uncertainty.** The model outputs non-crossing quantiles (5%, 50%, 95%) that never exceed rated power. Conformal calibration [6, 7], applied separately for each wind regime (below cut-in, steep part of the curve, rated, near cut-out), then guarantees the stated coverage, for example 90%."),
  bullet("**General and interpretable.** The same physics loss and uncertainty layer are tested on CNN–GRU, LSTM and a Transformer, and a constraint ablation shows which physical rule helps most at each forecast horizon."),

  heading("4. Research questions"),
  bullet("**RQ1.** Does adding power-curve physics to the loss reduce forecast error and physics violations compared with the constraint-aware CNN–GRU of [1]?"),
  bullet("**RQ2.** Can conformal calibration produce prediction intervals that achieve their stated coverage while remaining physically feasible?"),
  bullet("**RQ3.** Which physical constraints contribute most to accuracy, at which horizons, and how much do they help when training data are scarce?"),

  heading("5. Proposed methodology"),
  para("The study builds on the CNN–GRU of [1] and adds a wind-speed head, a quantile power head, a physics-informed loss and conformal calibration (Figure 1)."),
  new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: 60 },
    children: [new ImageRun({ type: "png", data: fs.readFileSync("fig1_pipeline.png"), transformation: { width: 600, height: 264 } })],
  }),
  caption("Figure 1. Proposed pipeline. Shaded stages are the contribution of this paper."),
  numbered("meth", "**Data preparation.** Remove curtailment, stoppages and faults using SCADA status codes; split chronologically into training, validation, calibration and test sets; normalise power by rated power."),
  numbered("meth", "**Baselines.** Persistence, LSTM, the CNN–GRU of [1] with capacity and ramp penalties, and a Transformer."),
  numbered("meth", "**Proposed model.** Inputs are past SCADA data (wind speed, direction, power, temperature), calendar features and, where available, numerical weather prediction (NWP) wind forecasts. Outputs for each horizon are a wind-speed forecast and non-crossing power quantiles bounded in [0, rated power]."),
  numbered("meth", "**Physics-informed loss.** The quantile (pinball) loss plus penalties for capacity, ramp rate, the power-curve band, cut-in/cut-out and wind–power consistency:"),
  new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 },
    children: runs("*L* = *L*_{pinball} + λ_{1}*L*_{cap} + λ_{2}*L*_{ramp} + λ_{3}*L*_{band} + λ_{4}*L*_{cut} + λ_{5}*L*_{cons}"),
  }),
  para("where *L*_{band} penalises forecast power outside a tolerance band δ around the fitted power curve Φ(*v*) [8, 9], and *L*_{cons} = ||*p̂* − Φ(*v̂*)||² penalises disagreement between forecast power *p̂* and the power curve of forecast wind *v̂*. Two variants are tested: (A) measured future wind speed used only as a training regulariser, and (B) the model's own wind forecast, as in *L*_{cons}.", { indent: { left: 360 }, alignment: AlignmentType.JUSTIFIED, spacing: { after: 60 } }),
  numbered("meth", "**Uncertainty.** Conformalized quantile regression [6] per horizon and wind regime, with adaptive updates to track seasonal drift [7]; a deep ensemble serves as an alternative."),
  numbered("meth", "**Tuning.** Penalty weights λ are chosen on the validation set after a warm-up period with the data loss only."),
  para("**Preliminary work.** A pilot pipeline (data cleaning, power-curve fitting, and plain versus physics-loss CNN–GRU) has been implemented; first results on Kelmarsh data will be shared for discussion.", { spacing: { before: 80, after: 100 }, alignment: AlignmentType.JUSTIFIED }),

  heading("6. Datasets"),
  para("The power-curve rules need measured wind speed, so the study uses public SCADA datasets that include it."),
  table([2700, 1100, 1250, 1600, 2824], [
    ["Dataset", "Turbines", "Resolution", "Period", "Role"],
    ["Kelmarsh wind farm, UK [10]", "6", "10 min", "2016–2024", "Main site"],
    ["SDWPF, KDD Cup 2022 [11]", "134", "10 min", "About 6 months", "Second site; generalisation"],
    ["ERA5 reanalysis [12]", "–", "Hourly", "Matching periods", "Weather (NWP-style) inputs"],
  ]),
  para("Both SCADA datasets include wind speed, wind direction, power and turbine status. Penmanshiel wind farm (same provider as Kelmarsh) is a backup second site.", { spacing: { before: 100, after: 100 }, alignment: AlignmentType.JUSTIFIED }),

  heading("7. Evaluation"),
  para("All models are compared at 4–6 horizons from 10 minutes to 6 hours, with and without the physics loss."),
  bullet("**Point accuracy:** RMSE and MAE, normalised by rated power."),
  bullet("**Probabilistic quality:** CRPS and pinball loss [13]."),
  bullet("**Interval quality:** coverage (PICP) against the nominal level, and normalised width (PINAW)."),
  bullet("**Physics consistency:** rate of violations (above rated power, below zero, outside the power-curve band, ramp limit exceeded)."),
  bullet("**Ablation and robustness:** each constraint removed in turn per horizon; training with reduced data (for example 3 months); SHAP on inputs as a supplement."),

  heading("8. Target journal, timeline and roles"),
  para("**Target journal:** *Energy Conversion and Management: X* (Elsevier, open access), which publishes AI-based renewable energy forecasting. Alternatives: *Applied Energy* and *Renewable Energy*. The final choice will be agreed together."),
  table([1300, 8174], [
    ["Month", "Work"],
    ["1", "Data cleaning, power-curve fitting, baselines (persistence, LSTM, CNN–GRU, Transformer)"],
    ["2", "Physics-informed loss (variants A and B) and quantile head"],
    ["3", "Conformal calibration, full experiments, second-site test, ablation"],
    ["4", "Paper writing, internal review and submission"],
  ]),
  para("**Roles:** Hasibur Rahman will carry out the coding, experiments and first draft. Dr Hossain will guide the method, review the results and manuscript, and co-author the paper.", { spacing: { before: 100, after: 100 }, alignment: AlignmentType.JUSTIFIED }),

  heading("References"),
  ...[
    "[[Hossain et al., 2025: full citation of the constraint-aware CNN–GRU wind power forecasting paper]]",
    "[[Hossain et al., 2024: full citation]]",
    "[[EAAI 2025 paper: full citation]]",
    "M. Raissi, P. Perdikaris, G. E. Karniadakis, “Physics-informed neural networks: A deep learning framework for solving forward and inverse problems involving nonlinear partial differential equations,” *J. Comput. Phys.*, vol. 378, pp. 686–707, 2019, doi:10.1016/j.jcp.2018.10.045.",
    "G. E. Karniadakis, I. G. Kevrekidis, L. Lu, P. Perdikaris, S. Wang, L. Yang, “Physics-informed machine learning,” *Nat. Rev. Phys.*, vol. 3, pp. 422–440, 2021, doi:10.1038/s42254-021-00314-5.",
    "Y. Romano, E. Patterson, E. J. Candès, “Conformalized quantile regression,” in *Advances in Neural Information Processing Systems (NeurIPS)*, 2019, arXiv:1905.03222.",
    "I. Gibbs, E. J. Candès, “Adaptive conformal inference under distribution shift,” in *Advances in Neural Information Processing Systems (NeurIPS)*, 2021, arXiv:2106.00170.",
    "C. Carrillo, A. F. Obando Montaño, J. Cidrás, E. Díaz-Dorado, “Review of power curve modelling for wind turbines,” *Renew. Sustain. Energy Rev.*, vol. 21, pp. 572–581, 2013, doi:10.1016/j.rser.2013.01.012.",
    "IEC 61400-12-1:2022, *Wind energy generation systems – Part 12-1: Power performance measurements of electricity producing wind turbines*, IEC, 2022.",
    "C. Plumley, “Kelmarsh wind farm data,” Cubico Sustainable Investments, Zenodo, v4, 2025. https://zenodo.org/records/16807551",
    "J. Zhou et al., “SDWPF: A dataset for spatial dynamic wind power forecasting challenge at KDD Cup 2022,” arXiv:2208.04360, 2022.",
    "H. Hersbach et al., “The ERA5 global reanalysis,” *Q. J. R. Meteorol. Soc.*, vol. 146, pp. 1999–2049, 2020, doi:10.1002/qj.3803.",
    "T. Gneiting, A. E. Raftery, “Strictly proper scoring rules, prediction, and estimation,” *J. Am. Stat. Assoc.*, vol. 102, pp. 359–378, 2007, doi:10.1198/016214506000001437.",
  ].map((r) => new Paragraph({
    numbering: { reference: "refs", level: 0 },
    children: runs(r, { size: 19 }),
    spacing: { after: 30 },
  })),
];

const numberedConfig = (reference, format, text) => ({
  reference,
  levels: [{ level: 0, format, text, alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 360, hanging: 360 } } } }],
});

const doc = new Document({
  creator: "Hasibur Rahman",
  title: "Physics-Informed, Uncertainty-Aware Short-Term Wind Power Forecasting – Concept Note",
  styles: {
    default: { document: { run: { font: FONT, size: SIZE, color: "000000" } } },
    paragraphStyles: [{
      id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { font: FONT, size: 24, bold: true, color: "000000" },
      paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 0, keepNext: true },
    }],
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 260 } } } }] },
      numberedConfig("prob", LevelFormat.DECIMAL, "%1."),
      numberedConfig("meth", LevelFormat.DECIMAL, "%1."),
      { reference: "refs", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "[%1]", alignment: AlignmentType.LEFT,
        style: { run: { size: 19 }, paragraph: { indent: { left: 480, hanging: 480 } } } }] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1247, bottom: 1247, left: 1216, right: 1216 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], size: 18 })] })] }) },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("Concept_Note_Physics_Informed_Wind_Forecasting.docx", buf);
  console.log("written");
});
