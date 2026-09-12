"""只复现搜索首组最初三日的输入边界，不写全年结果或启动参数搜索。"""
from pathlib import Path
import sys
import json
from unittest.mock import patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.q4.inputs import load_inputs,protect
from src.q4.annual import run_dates
from src.q3.annual import FORMAL_DATES
from src.q3.optimizer import solve_actual_step


def main():
    report = dict(alpha=.8,**{"lambda":0.},scope="first three days only",reproduced=False)
    def inspect(*args,**kwargs):
        arrays = {k:np.asarray(v,float) for k,v in zip(("load_forecast","pv_forecast","price","commitment"),args[3:7])}
        if any((a<0).any() for a in arrays.values()):
            report.update(reproduced=True,date=str(args[9]),slot=args[0],inputs={
                k:dict(minimum=float(a.min()),negative_count=int((a<0).sum()),
                       minimum_negative=float(a[a<0].min()) if (a<0).any() else None) for k,a in arrays.items()})
        return solve_actual_step(*args,**kwargs)
    with protect(ROOT):
        history,prices,issues = load_inputs(ROOT)
        try:
            with patch("src.q3.simulation.solve_actual_step",side_effect=inspect):
                run_dates(history,prices,issues,3,FORMAL_DATES[:3],"BOUNDARY DIAGNOSTIC ONLY",.8,0.)
        except ValueError as error:
            report["error"] = str(error)
        folder = ROOT/"outputs/q4/diagnostics"
        folder.mkdir(parents=True,exist_ok=True)
        (folder/"negative_input_reproduction.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
