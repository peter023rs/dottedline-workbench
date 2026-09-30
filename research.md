# Dotted/dashed line restoration with meaning preserved

Research checked 2026-09-30. This is a design synthesis, not a claim to reproduce any paper or its reported accuracy. Sources below are publisher pages, author-hosted papers, institutional repositories, and the original preprint.

## Recommendation

Represent every detected line as **continuous geometry + original visual pattern + separately verified engineering meaning**. Fill the gaps only in a derived tracing layer. Preserve the original drawing, dash intervals, source locations, uncertainty, and review decisions. “Straight” here should mean continuously traceable: preserve genuine corners and bends instead of replacing an entire routed connection by its endpoint chord.

A solid output image alone cannot retain the distinction between a process pipe, control signal, boundary, hidden line, and other drawing conventions. A continuous SVG or raster plus structured metadata is the practical deliverable. The drawing's own legend and context should determine engineering meaning; until verified, retain `unknown`, independently of a confident `dashed` visual classification.

## Evidence and what to borrow

### 1. Dori, Wenyin and Peleg, *How to Win a Dashed Line Detection Contest* (GREC 1995; proceedings 1996)

**Paper claim:** its mechanism incrementally recovers components satisfying continuity conditions. The contest included straight, curved, dashed and dash-dot lines with interwoven text. The publisher abstract reports successful detection on the contest drawings. The complete chapter was subscription-only during this investigation; detailed parameter values were not independently verified.

**Our adaptation:** grow compatible component chains in both directions; score alignment, width, spacing and support. This is an inspiration, not an exact reimplementation or a transfer of the contest result to P&IDs.

[Publisher and DOI](https://link.springer.com/chapter/10.1007/3-540-61226-2_23)

### 2. Agam, Luo and Dinstein, *Morphological Approach for Dashed Lines Detection* (GREC 1995; proceedings 1996)

**Paper claim:** locally adapted tube-directional morphological operators detect and label dashed lines, including intersecting lines. Its stated input is an image of dashes, following separation of graphics, text, symbols and dashes. Only the publisher abstract was accessible.

**Our adaptation:** directional closing is useful to propose candidate corridors or as a baseline. Applying one large closing kernel indiscriminately to the full P&ID is not equivalent to this method. Verify the original stroke sequence before accepting a proposed bridge.

[Publisher and DOI](https://link.springer.com/chapter/10.1007/3-540-61226-2_9)

### 3. Jonk, van den Boomgaard and Smeulders, *Grammatical Inference of Dashed Lines* (CVIU 1999)

**Paper claim:** a dashed line consists of a centerline and repeating grammar. The grammar carries distinctions such as hidden lines versus centerlines. The work treats geometry localization separately from grammar inference and matches repeating symbolic sequences with error-tolerant operations. The author's thesis chapter explicitly warns that morphological joining can lose grammar and merge different collinear lines.

**Our adaptation:** record ordered dash/dot and gap measurements before reconstruction. Compare repeating patterns and split chains when the pattern changes. A few robust pattern classes are useful initially; implementing the paper's general grammar inference is a separate enhancement.

[Publisher](https://www.sciencedirect.com/science/article/abs/pii/S1077314299907531) | [Author's institutional thesis chapter](https://pure.uva.nl/ws/files/3552594/20994_UBA002000817_08.pdf)

### 4. Debled-Rennesson and Wendling, *Combining Force Histogram and Discrete Lines to Extract Dashed Lines* (ICPR 2010)

**Paper claim:** component-pair spatial relationships, repeating local patterns and bounding discrete lines support propagation through noise and occlusion. It considers nearby components rather than every pair. Local kernel patterns have two or three components; final accepted sequences contain more than three segments. Several thresholds can be estimated from the image.

**Our adaptation:** derive scale and spacing from the document, use neighborhood searches, and require several repeating strokes. A gap threshold must scale with the image and observed pattern. A fixed 10-pixel rule cannot be expected to generalize across DPI.

[Original conference paper hosted by CNRS/LIRIS](https://projet.liris.cnrs.fr/imagine/pub/proceedings/ICPR-2010/data/4109b574.pdf)

### 5. Liu et al., *Neural Recognition of Dashed Curves with Gestalt Law of Continuity* (CVPR 2022)

**Paper claim:** a Transformer framework jointly estimates curve instances, their raster “Visual Form,” and a continuous vector “Semantic Curve.” It uses synthetic training examples and real examples including sewing and graphic designs. The authors note ambiguity with double lines and substantial computational cost.

**Our adaptation:** borrow the explicit separation between observed dashes and continuous geometry. Here the paper's “semantic” means the perceived curve instance; it does **not** assign P&ID signal or process meaning. A trained model could later help with irregular curved routes, but its published results do not establish performance on this user's P&ID.

[Official CVPR paper](https://openaccess.thecvf.com/content/CVPR2022/papers/Liu_Neural_Recognition_of_Dashed_Curves_With_Gestalt_Law_of_Continuity_CVPR_2022_paper.pdf) | [Author project](https://ttwong12.github.io/papers/dashline/dashline.html)

### 6. *End-to-end Digitization of Image Format Piping and Instrumentation Diagrams at an Industrially Applicable Level* (JCDE 2022)

**Paper claim:** line signs and flow arrows are detected separately from continuous lines. Lines overlapping symbol/text regions are excluded from the pure-line list. Overlapping line signs transfer their type onto continuous lines, and arrow information supplies direction. The workflow includes thinning before Hough-based extraction.

**Our adaptation:** keep independent stages for geometry, visual class, semantic signs and direction. Avoid interpreting strokes inside text or symbols as candidate dashes. Transfer a semantic label only with sign, legend or review evidence; geometric proximity alone is insufficient.

[Open-access original paper, sections 4.3.1-4.3.3](https://academic.oup.com/jcde/article/9/4/1298/6611631)

### 7. Han et al., *Rule-based Continuous Line Classification Using Shape and Positional Relationships Between Objects in Piping and Instrumentation Diagram* (Expert Systems with Applications 2024)

**Paper claim:** eight continuous-line categories are distinguished using shapes and object relationships, including drain, annotation, spec break, dimension, extension and leader lines. This reinforces that continuous appearance alone does not determine engineering role. The public publisher/institutional abstracts were inspected, not a complete reproduction.

**Our adaptation:** do not change the semantic class to “pipe” merely because rendering became solid. Keep context and semantic provenance as attributes independent of appearance.

[Publisher](https://www.sciencedirect.com/science/article/abs/pii/S0957417424002318) | [Author institution](https://pure.korea.ac.kr/en/publications/rule-based-continuous-line-classification-using-shape-and-positio/)

### 8. *Advanced Integration of Discrete Line Segments in Digitized P&ID for Continuous Instrument Connectivity* (2025 preprint)

**Paper scope:** links detected line fragments and equipment into a digitized P&ID connectivity representation. This is relevant to the downstream tracing objective, but is a preprint and not evidence that gap filling alone recovers correct engineering topology.

**Our adaptation:** evaluate endpoint connectivity separately from pixel continuity. A bridge that looks clean but connects the wrong devices is an error.

[Original preprint](https://arxiv.org/abs/2505.11976) | [PDF](https://arxiv.org/pdf/2505.11976)

## Implementable pipeline for this workbench

The following are our engineering choices, informed by the above evidence:

1. Keep the original source. Prefer reliable PDF path/dash information when present; for scans, rasterize at a known scale and binarize conservatively.
2. Extract small components or short stroke runs. Estimate stroke width. Exclude known text, symbols and drawing borders when reliable masks are available. Do not discard round dots solely for having low aspect ratio.
3. Group collinear strokes using perpendicular offset, direction, width and a bounded gap. Search arbitrary angles if required; label an axis-only implementation honestly.
4. Validate a chain against the unmodified pixels: several repeats, consistent spacing, plausible dash lengths and limited lateral deviation. Keep ambiguous chains for review. A normal broken solid stroke is not automatically a dashed line.
5. Classify observed style (`dotted`, `dashed`, `dash_dot`, or `unknown`) using the sequence. Save actual evidence even when the style classifier is uncertain.
6. Create a continuous centerline or polyline and an independent bridge mask. Join only accepted local gaps. Preserve bends. Do not extrapolate arbitrary distances to symbols.
7. Export geometry with stable IDs, source coordinates, observed intervals, inferred gaps, visual style, quality score, semantic class, semantic evidence and review status. Treat a heuristic quality score as a ranking, not a calibrated probability.
8. Keep crossing and junction decisions separate. The fact that two reconstructed lines intersect does not prove a connection. Likewise, endpoint proximity alone does not prove attachment to a symbol.

## What testing can establish

- Synthetic truth: dashed, dotted, dash-dot, multiple widths and DPI, diagonal runs, close parallel lines, corners, crossings, solid lines, text-like distractors and interrupted solid strokes.
- Real drawing: manually inspect representative crops and rejected candidates, preserving source crop coordinates. Count false joins and missed runs against explicit annotations. Candidate counts are not accuracy.
- Compare version 1 and the new algorithm on the same raster and settings where meaningful. Report changes in false bridges, recovered gaps, endpoint error and preserved visual labels.
- Separate geometric, visual-style and semantic evaluation. Review labels can preserve engineering meaning; inferred style alone cannot prove it.
- Do not report diagram-wide precision/recall without a complete matching ground truth. Synthetic success and a real-sheet demonstration are different evidence levels.

## Boundaries

None of the inspected research establishes that converting every dotted line into black solid pixels alone improves a general AI model's P&ID comprehension. That requires a downstream tracing/understanding comparison. This workbench should produce inspectable candidate geometry and retain information needed for that evaluation. Dense text, low resolution, irregular dashes, dash-dot families, occlusion, bends and crossing topology remain cases requiring explicit validation.
