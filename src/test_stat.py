import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from math import radians, sin, cos, sqrt, atan2
import sqlite3
from ground_truth_validator import load_walker_sites

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

# ─── Carrega Walker ───
walker = [(s['lat'], s['lon']) for s in load_walker_sites()]
print(f"Walker: {len(walker)} jaciments")

# ─── Monte Carlo ───
N_SIM = 1000
N_CAND = 130
THRESHOLD = 50
OBSERVED = 43.1

print(f"Executant {N_SIM} simulacions...")
hit_rates = []
for i in range(N_SIM):
    if i % 100 == 0:
        print(f"  {i}/{N_SIM}...")
    rlat = np.random.uniform(-20, 5, N_CAND)
    rlon = np.random.uniform(-80, -45, N_CAND)
    hits = sum(1 for lat, lon in zip(rlat, rlon)
               if min(haversine(lat, lon, w[0], w[1]) for w in walker) < THRESHOLD)
    hit_rates.append(hits / N_CAND * 100)

hit_rates = np.array(hit_rates)
mean_r = hit_rates.mean()
std_r = hit_rates.std()
z = (OBSERVED - mean_r) / std_r

# p-value empíric: quantes simulacions superen l'observat
p_emp = np.mean(hit_rates >= OBSERVED)
p_text = "< 0.001" if p_emp == 0 else f"= {p_emp:.4f}"

print(f"\nAleatori: {mean_r:.1f}% ± {std_r:.1f}%")
print(f"Observat: {OBSERVED}%   Z = {z:.1f}   p {p_text}")

# ─── PALETA (igual que el TFG) ───
INK   = "#14241F"
GOLD  = "#C8973F"
CLAY  = "#B85042"
MOSS  = "#5C8A5A"
PAPER = "#F4F1E8"
SLATE = "#5A6B63"

# ─── GRÀFIC ───
plt.rcParams['font.family'] = 'DejaVu Sans'
fig, ax = plt.subplots(figsize=(11, 6), dpi=150)
fig.patch.set_facecolor(PAPER)
ax.set_facecolor(PAPER)

# Histograma de la distribució aleatòria
n, bins, patches = ax.hist(hit_rates, bins=35, color=MOSS, alpha=0.55,
                            edgecolor=INK, linewidth=0.5, label='Distribució aleatòria (1.000 simulacions)')

# Corba normal teòrica superposada
x = np.linspace(hit_rates.min() - 2, max(hit_rates.max(), OBSERVED) + 3, 300)
normal = (1 / (std_r * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean_r) / std_r) ** 2)
normal_scaled = normal * len(hit_rates) * (bins[1] - bins[0])
ax.plot(x, normal_scaled, color=INK, linewidth=2, linestyle='-', alpha=0.7, label='Ajust normal')

# Línia de la mitjana aleatòria
ax.axvline(mean_r, color=SLATE, linewidth=2, linestyle='--',
           label=f'Mitjana aleatòria: {mean_r:.1f}%')

# Banda ±1 desviació estàndard
ax.axvspan(mean_r - std_r, mean_r + std_r, color=SLATE, alpha=0.12,
           label=f'±1σ ({std_r:.1f}%)')

# Línia de l'observat (la nostra)
ax.axvline(OBSERVED, color=CLAY, linewidth=3.5,
           label=f'Sistema (observat): {OBSERVED}%')

# Fletxa anotant l'observat
ymax = max(n) * 1.05
ax.annotate(f'{OBSERVED}%\nZ = {z:.1f}\np {p_text}',
            xy=(OBSERVED, ymax * 0.35),
            xytext=(OBSERVED - 9, ymax * 0.72),
            fontsize=13, fontweight='bold', color=CLAY,
            ha='center',
            arrowprops=dict(arrowstyle='->', color=CLAY, lw=2.5))

# Etiquetes i títol
ax.set_xlabel('Hit rate (%)', fontsize=13, color=INK, fontweight='bold')
ax.set_ylabel('Freqüència (nombre de simulacions)', fontsize=13, color=INK, fontweight='bold')
ax.set_title('Significança estadística del sistema (test de Monte Carlo)',
             fontsize=16, color=INK, fontweight='bold', pad=16)

# Estètica eixos
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color(SLATE)
ax.spines['bottom'].set_color(SLATE)
ax.tick_params(colors=INK, labelsize=11)

# Llegenda
ax.legend(loc='upper right', fontsize=10.5, framealpha=0.95,
          edgecolor=SLATE, facecolor='white')

# Caixa de text amb conclusió
textstr = (f'El sistema supera la base aleatòria en {OBSERVED - mean_r:.1f} punts\n'
           f'({z:.1f} desviacions estàndard, p {p_text}).\n'
           f'La correlació NO és atribuïble a l\'atzar.')
props = dict(boxstyle='round,pad=0.6', facecolor=GOLD, alpha=0.25, edgecolor=GOLD)
ax.text(0.025, 0.97, textstr, transform=ax.transAxes, fontsize=11,
        verticalalignment='top', bbox=props, color=INK)

plt.tight_layout()
plt.savefig('montecarlo_validacio.png', dpi=200, bbox_inches='tight', facecolor=PAPER)
print("\nGuardat: montecarlo_validacio.png")
plt.show()