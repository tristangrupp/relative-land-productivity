"""Why summary cells of the decision view are gray ("no action stands out"), per state and for
the Amazon biome (investigation of 17 November 2026, WORKLOG.md). Reads analysis\decisions\fields.

  python s11_gray_cells.py
"""
import sys, os, json, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\grupp\src\relative-land-productivity\pipeline")
import s04_common as C
D = os.path.join(C.ANALYSIS, "decisions", "fields")
states = C.state_dirs(2024)
df = pd.concat([pd.read_parquet(os.path.join(D, f"{s}.parquet"), columns=["state","cell6","decision","decision_computed","change_class","crop_2024","confidence_low","source","area_decision","biome"]) for s in states], ignore_index=True)
for c in ("decision","decision_computed","change_class","area_decision"): df[c]=df[c].astype(str)
PASSIVE = ["keep","intensify","none","low_confidence"]
trusted = df.decision != "low_confidence"
nat = df.loc[trusted,"decision"].value_counts(normalize=True)
g = df.groupby("cell6")
cells = pd.DataFrame({"n": g.size(), "n_trusted": trusted.groupby(df.cell6).sum(), "state": g["state"].agg(lambda x: x.mode().iat[0]),
                      "biome": g["biome"].agg(lambda x: x.mode().iat[0])})
cnt = df[trusted].groupby(["cell6","decision"]).size().rename("k").reset_index()
cnt["share"] = cnt.k / cnt.cell6.map(cells.n_trusted); cnt["lift"] = cnt.share / cnt.decision.map(nat)
act = cnt[~cnt.decision.isin(PASSIVE) & (cnt.share>=0.15) & (cnt.lift>=1.5) & (cnt.cell6.map(cells.n_trusted)>=10)]
top = act.sort_values("lift").drop_duplicates("cell6", keep="last").set_index("cell6").decision
cells["top"] = top
cells["reason"] = np.where(cells.top.notna(), "colored", np.where(cells.n_trusted < 10, "under 10 trusted fields", "trusted fields but no action reaches 15% and 1.5x"))
def rep(name, mask_cells):
    c = cells[mask_cells]; f = df[df.cell6.isin(c.index)]
    print(f"\n== {name}: {len(c)} cells, {len(f)} fields")
    print(c.reason.value_counts().to_string())
    gray = c[c.reason!="colored"].index
    fg = f[f.cell6.isin(gray)]
    print(" gray cells fields:", len(fg), " low conf share", round(fg.confidence_low.mean(),3), " source", fg.source.value_counts().to_dict())
    print(" gray: shown decision", (fg.decision.value_counts(normalize=True).head(6).round(3)).to_dict())
    print(" gray: computed decision", (fg.decision_computed.value_counts(normalize=True).head(8).round(3)).to_dict())
    print(" gray: crop 2024 pasture share", round((fg.crop_2024==15).mean(),3), " change_class", fg.change_class.value_counts(normalize=True).head(5).round(3).to_dict())
    print(" gray: area call", fg.area_decision.value_counts(normalize=True).round(3).to_dict())
    # what would top be on computed decisions
    cc = fg.groupby(["cell6","decision_computed"]).size().rename("k").reset_index()
    cc["share"]=cc.k/cc.cell6.map(fg.groupby("cell6").size())
    natc = df.decision_computed.value_counts(normalize=True)
    cc["lift"]=cc.share/cc.decision_computed.map(natc)
    a2 = cc[~cc.decision_computed.isin(PASSIVE) & (cc.share>=0.15) & (cc.lift>=1.5)].sort_values("lift").drop_duplicates("cell6",keep="last")
    print(" gray cells that would color on computed calls:", len(a2), "of", len(gray), a2.decision_computed.value_counts().head(6).to_dict())
uf = C.state_uf_map(2024)
for st in ["Amazonas","Para","Acre","Rondonia","Roraima","Amapa","Maranhao","Tocantins","Mato_Grosso"]:
    rep(st, cells.state==st)
rep("Amazon biome", cells.biome==1)
