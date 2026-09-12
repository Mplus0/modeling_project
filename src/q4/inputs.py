"""只读输入和冻结文件SHA保护，时间解析复用既有预处理约定。"""

from contextlib import contextmanager
from io import StringIO
import pandas as pd
import numpy as np
from src.common.data_loader import file_hash
from src.q2.forecasting import load_daily_inputs
from src.q3.forecast import load_hourly_forecasts


def frozen_hashes(root):
    folders = ["data","src/common","src/q1","src/q2","src/q3","outputs"]
    return {str(p.relative_to(root)):file_hash(p) for name in folders for p in (root/name).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and not p.is_relative_to(root/"outputs/q4")
            and p not in (root/"outputs/submissions/result4-2.xlsx",root/"outputs/submissions/result4-3.xlsx")}


@contextmanager
def protect(root):
    before = frozen_hashes(root)
    try:
        yield before
    finally:
        if frozen_hashes(root)!=before:
            raise RuntimeError("Q4检测到冻结文件SHA-256变化")


def load_inputs(root):
    directory = root/"data/processed"
    power = pd.read_csv(directory/"historical_power.csv",float_precision="round_trip")
    frame = pd.read_csv(directory/"electricity_price.csv",float_precision="round_trip")
    axes = ["datetime","source_date","source_time"]
    if not frame[axes].equals(power[axes]) or len(frame)!=52560:
        raise ValueError("Q4动态价格与负荷/PV时间轴未逐位置对齐")
    if not np.isfinite(frame.price_yuan_per_kwh).all() or (frame.price_yuan_per_kwh<0).any():
        raise ValueError("动态价格含负值或非有限数值")
    # 只在内存适配Q2加载器的144行价格接口，复用其负荷/PV时间解析；该返回价格不用于Q4决策。
    price_view = pd.DataFrame(dict(slot=np.arange(1,145),price_yuan_per_kwh=frame.price_yuan_per_kwh.iloc[:144].to_numpy()))
    history,_ = load_daily_inputs(directory/"historical_power.csv",StringIO(price_view.to_csv(index=False)))
    prices = {pd.Timestamp(d).date():g.price_yuan_per_kwh.to_numpy(float) for d,g in frame.groupby("source_date",sort=False)}
    return history,prices,load_hourly_forecasts(directory/"pv_forecast_hourly.csv")
