"""Modèle hydrologique conceptuel GR4J (Perrin, Michel, Andréassian, 2003).

Implémentation journalière classique :
  - réservoir de production (capacité X1),
  - percolation,
  - deux hydrogrammes unitaires UH1 (base X4) et UH2 (base 2*X4),
  - échange souterrain (X2),
  - réservoir de routage (capacité X3).

Les débits produits sont exprimés en mm/jour sur le bassin ;
la conversion en m³/s se fait avec la surface du bassin versant.
"""


def _s_curve_1(t: float, x4: float) -> float:
    """Courbe S de UH1 (base x4 jours)."""
    if t <= 0:
        return 0.0
    if t >= x4:
        return 1.0
    return (t / x4) ** 2.5


def _s_curve_2(t: float, x4: float) -> float:
    """Courbe S de UH2 (base 2*x4 jours)."""
    if t <= 0:
        return 0.0
    if t >= 2 * x4:
        return 1.0
    if t < x4:
        return 0.5 * (t / x4) ** 2.5
    return 1.0 - 0.5 * ((2 * x4 - t) / x4) ** 2.5


def _unit_hydrographs(x4: float):
    """Poids discrétisés des hydrogrammes unitaires UH1 et UH2."""
    n1 = int(x4) + 1
    n2 = int(2 * x4) + 1
    uh1, uh2 = [], []
    for k in range(1, n1 + 1):
        uh1.append(_s_curve_1(k, x4) - _s_curve_1(k - 1, x4))
    for k in range(1, n2 + 1):
        uh2.append(_s_curve_2(k, x4) - _s_curve_2(k - 1, x4))
    return uh1, uh2


class GR4J:
    """Modèle GR4J avec état interne persistant (permet de poursuivre une
    simulation, notamment pour la prévision)."""

    def __init__(self, x1=350.0, x2=0.0, x3=90.0, x4=1.7,
                 s0_ratio=0.5, r0_ratio=0.5):
        self.x1, self.x2, self.x3, self.x4 = x1, x2, x3, x4
        self.s = s0_ratio * x1          # réservoir de production [mm]
        self.r = r0_ratio * x3          # réservoir de routage [mm]
        self.uh1, self.uh2 = _unit_hydrographs(x4)
        # historique des entrées pour la convolution des UH
        self.hist1 = [0.0] * len(self.uh1)
        self.hist2 = [0.0] * len(self.uh2)

    @property
    def state(self):
        return {"production_store": self.s, "routing_store": self.r}

    def _convolve(self, hist, weights):
        return sum(w * v for w, v in zip(weights, hist))

    def step(self, p: float, e: float) -> float:
        """Un pas de temps journalier. p, e : pluie et ETP [mm/j].
        Retourne le débit en mm/j sur le bassin."""
        x1, x2, x3 = self.x1, self.x2, self.x3

        # --- Entrées nettes ---
        if p >= e:
            pn, en = p - e, 0.0
        else:
            pn, en = 0.0, e - p

        # --- Réservoir de production ---
        if pn > 0:
            sr = self.s / x1
            ps = x1 * (1 - sr * sr) * _tanh(pn / x1) / (1 + sr * _tanh(pn / x1))
        else:
            ps = 0.0
        if en > 0:
            sr = self.s / x1
            es = self.s * (2 - sr) * _tanh(en / x1) / (1 + (1 - sr) * _tanh(en / x1))
        else:
            es = 0.0
        self.s = max(0.0, self.s - es + ps)

        # --- Percolation ---
        perc = self.s * (1.0 - (1.0 + (4.0 * self.s / (9.0 * x1)) ** 4) ** -0.25)
        self.s = max(0.0, self.s - perc)

        # --- Pluie efficace ---
        pr = perc + max(0.0, pn - ps)

        # --- Hydrogrammes unitaires (convolution) ---
        self.hist1 = [0.9 * pr] + self.hist1[:-1]
        self.hist2 = [0.1 * pr] + self.hist2[:-1]
        q9 = self._convolve(self.hist1, self.uh1)
        q1 = self._convolve(self.hist2, self.uh2)

        # --- Échange souterrain ---
        f = x2 * (self.r / x3) ** 3.5 if self.r > 0 else 0.0

        # --- Réservoir de routage ---
        self.r = max(0.0, self.r + q9 + f)
        qr = self.r * (1.0 - (1.0 + (self.r / x3) ** 4) ** -0.25)
        self.r = max(0.0, self.r - qr)

        # --- Débit direct ---
        qd = max(0.0, q1 + f)

        return qr + qd   # [mm/j]


def _tanh(x: float) -> float:
    import math
    return math.tanh(x)


def run_series(precip, etp, params=None, area_km2=1.0):
    """Simule une série complète. precip, etp : listes de mm/j.
    Retourne (flows_mm, flows_m3s) pour toute la série, incluant la
    montée en régime (les premiers pas sont moins fiables)."""
    model = GR4J(**(params or {}))
    flows_mm = [model.step(p, e) for p, e in zip(precip, etp)]
    flows_m3s = [q * area_km2 / 86.4 for q in flows_mm]
    return flows_mm, flows_m3s