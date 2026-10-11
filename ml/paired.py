"""Paired, family-bootstrapped comparison of two lab runs: model organ-rho of A minus B on the same held-out priors."""
import sys, pickle
sys.path.insert(0, "/home/hyeongchanahn/CONI/adctox/ml")
import lab
C = "/data/hyeongchanahn/adctox/ml_cache/"
def paired(a, b, regime, key="model"):
    A, B = pickle.load(open(C + f"lab_{a}.pkl", "rb"))[regime][key], pickle.load(open(C + f"lab_{b}.pkl", "rb"))[regime][key]
    return lab.fam_boot(lab.load_rows(), A, B)
if __name__ == "__main__":
    a, b = sys.argv[1], sys.argv[2]
    for reg in sys.argv[3:] or ["prior", "cluster"]:
        r = paired(a, b, reg); print(f"{a} - {b} | {reg}: organ-rho {r['delta']:+.4f} [{r['lo']:+.4f}, {r['hi']:+.4f}] over {r['n']} held-out diseases")
