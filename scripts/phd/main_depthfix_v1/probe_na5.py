"""inspection only: value counts of the 나5 columns that define the new target type."""
import pandas as pd
for p in ['ALS', 'LoD2']:
    d = pd.read_csv(f'/df/input/na5/patches_{p}.csv.gz', usecols=['patch_id', 'kind', 'initial_state', 'A2_n', 'none_n', 'none_significant', 'combo_D_returned', 'combo_D_judgment', 'mix_large', 'A2_c_ge5_frac', 'L_m', 'd_m'])
    print(p, len(d), flush=True)
    print(d.groupby(['combo_D_judgment', 'none_significant', 'mix_large', 'combo_D_returned'], dropna=False).size().to_string())
    print('c_ge5 nan among sig&big', d[(d.none_significant) & (d.mix_large == 1)].A2_c_ge5_frac.isna().sum())
