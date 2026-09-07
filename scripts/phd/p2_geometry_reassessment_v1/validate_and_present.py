"""Check aggregation identities and present existing reanalysis tables; no scene rendering."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    heights = read(args.analysis/"paired_reference_height.csv")
    pairs = read(args.analysis/"paired_reference.csv")
    cells = read(args.analysis/"xy_cells.csv")
    areas = read(args.analysis/"prediction_distance_area.csv")
    global_rows = read(args.analysis/"global_recomputed.csv")
    receipt = json.loads((args.analysis/"receipt.json").read_text())
    assert receipt["inputs_unchanged"] and receipt["scientific_verdict"] is None
    checks = []
    for pair in pairs:
        selected = [r for r in heights if all(r[k] == pair[k] for k in ("resolution","setting","threshold_m"))]
        for field in ("reference_points","gained_reference","lost_reference"):
            expected = int(pair["n_reference" if field == "reference_points" else field])
            assert sum(int(r[field]) for r in selected) == expected
        assert abs(sum(float(r["contribution_to_global_recall_change"]) for r in selected)-float(pair["recall_change"])) < 1e-12
    for row in global_rows:
        if row["setting"] != "sample0.1_reference0.1" or float(row["threshold_m"]) != 0.5:
            continue
        selected = [r for r in areas if r["candidate"] == row["candidate"]]
        assert abs(sum(float(r["area_estimate_m2"]) for r in selected)-float(row["area_m2"])) < 1e-8
    for resolution in ("512","1024"):
        for pair in [p for p in pairs if p["resolution"]==resolution and float(p["threshold_m"])==0.5]:
            band = next(r for r in heights if r["resolution"]==resolution and r["setting"]==pair["setting"] and float(r["threshold_m"])==0.5 and int(r["z_lower_m"])==-44)
            net = int(pair["lost_reference"])-int(pair["gained_reference"])
            band_net = int(band["lost_reference"])-int(band["gained_reference"])
            checks.append(dict(resolution=resolution,setting=pair["setting"],threshold_m=0.5,
                total_net_recall_loss_points=net,z_minus44_to_minus42_net_loss=band_net,
                band_share_of_net_recall_loss=band_net/net,
                band_share_of_gross_lost_points=int(band["lost_reference"])/int(pair["lost_reference"])))
    fig,axes = plt.subplots(1,2,figsize=(12,5.8),layout="constrained",sharey=True,sharex=True)
    for ax,res in zip(axes,("512","1024")):
        selected=[r for r in heights if r["resolution"]==res and r["setting"]=="sample0.1_reference0.1" and float(r["threshold_m"])==0.5]
        y=np.arange(len(selected))
        ax.barh(y,[int(r["gained_reference"]) for r in selected],color="#287db4",label="Newly within 0.5 m")
        ax.barh(y,[-int(r["lost_reference"]) for r in selected],color="#d66549",label="No longer within 0.5 m")
        ax.axvline(0,color="black",lw=.7)
        ax.set(yticks=y,yticklabels=[f"[{r['z_lower_m']}, {r['z_upper_m']})" for r in selected],
               xlim=(-75000,25000),xlabel="Same-reference point count",title=f"Mesh resolution {res}")
        ax.legend(loc="lower right",fontsize=8)
    axes[0].set_ylabel("Local Z band (m); not semantic classes")
    fig.suptitle("P2: gains and losses in reference coverage\nAll height bands; unchanged 0.5 m distance threshold")
    fig.savefig(args.output/"recall_height_contributions.png",dpi=170,bbox_inches="tight")
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5.7),layout="constrained")
    for ax,res in zip(axes,("512","1024")):
        selected=[r for r in cells if r["resolution"]==res]
        sc=ax.scatter([float(r["x_m"])+.25 for r in selected],[float(r["y_m"])+.25 for r in selected],
                      c=[float(r["mean_distance_change_m"]) for r in selected],s=8,marker="s",cmap="RdBu_r",vmin=-1,vmax=1)
        ax.set(xlim=(110,158),ylim=(86,132),aspect="equal",xlabel="Local X (m)",ylabel="Local Y (m)",title=f"Mesh resolution {res}")
    bar=fig.colorbar(sc,ax=axes,shrink=.85)
    bar.set_label("Distance change (m): blue = closer, red = farther",fontsize=9)
    fig.suptitle("P2: current UAS-to-surface distance change\nReduced prior minus native; 0.5 m XY cells; colors clipped at +/-1 m")
    fig.savefig(args.output/"xy_distance_change.png",dpi=170,bbox_inches="tight")
    plt.close(fig)
    summary=dict(scientific_verdict=None,status="PASS_AGGREGATION_AND_PRESENTATION_CHECKS",
        height_partition_pairs_checked=len(pairs),area_partition_models_checked=4,
        interpretation="Share with caveats: descriptive same-reference decomposition, not causal or semantic building evaluation",
        low_height_recall_loss_decomposition=checks,
        source_csv_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.analysis.glob("*.csv")},
        presentation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output/"validation.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
    print(json.dumps(summary["low_height_recall_loss_decomposition"],indent=2))


if __name__ == "__main__":
    main()
