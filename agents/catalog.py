"""Catalogue de toutes les données suivies : d'où elles viennent et comment les afficher.

Champs principaux :
- kind    : "rate" (taux en %, variations en points de base) ou "price" (variations en %)
- freq    : "daily", "monthly" ou "quarterly" (sert à détecter les retards)
- fetch   : (fonction source, arguments) ; "yahoo" est traité à part (appel groupé)
- derive  : donnée calculée à partir d'autres (spreads, pentes, proxies)
- transform : "yoy" = glissement annuel calculé depuis un indice ; "mom_diff" = variation mensuelle
- restricted : licence qui interdit de republier le niveau (ICE) -> on n'affiche que les variations
- na      : donnée sans source gratuite fiable -> toujours « n.d. » avec la raison
"""
from agents import sources as S

FRED = "FRED (Fed de St. Louis)"
ECB = "BCE – Data Portal"
BBK = "Bundesbank"
BOE = "Bank of England"
BOJ = "Banque du Japon"
MOF = "Ministère des Finances (Japon)"
ESTAT = "Eurostat"
YAHOO = "Yahoo Finance (différé)"

GROUPS = [
    ("policy", "Taux directeurs"),
    ("short", "Taux courts"),
    ("govt", "Souverains 10 ans & courbe"),
    ("spreads", "Spreads & pentes"),
    ("expect", "Anticipations"),
    ("fx", "Change"),
    ("equity", "Actions"),
    ("vol", "Volatilité"),
    ("credit", "Crédit (OAS)"),
    ("commo", "Matières premières & crypto"),
    ("macro", "Dernières publications macro"),
]

SERIES = [
    # ---------------------------------------------------------- Taux directeurs
    dict(id="fed_upper", group="policy", label="Fed funds – borne haute", kind="rate", freq="daily",
         source=FRED, fetch=(S.fred, "DFEDTARU"), display="fed_range", hidden=False),
    dict(id="fed_lower", group="policy", label="Fed funds – borne basse", kind="rate", freq="daily",
         source=FRED, fetch=(S.fred, "DFEDTARL"), hidden=True),
    dict(id="ecb_dfr", group="policy", label="BCE – taux de dépôt", kind="rate", freq="event",
         source=ECB, fetch=(S.ecb, "FM", "B.U2.EUR.4F.KR.DFR.LEV", 3650)),
    dict(id="boe_bank", group="policy", label="BoE – Bank Rate", kind="rate", freq="daily",
         source=BOE, fetch=(S.boe, "IUDBEDR")),
    dict(id="boj_call", group="policy", label="BoJ – taux call JJ (cible de politique)", kind="rate",
         freq="daily", source=BOJ, fetch=(S.boj, "FM01", "STRDCLUCON"),
         note="Taux au jour le jour non garanti effectif, que la BoJ pilote."),
    # ---------------------------------------------------------- Taux courts
    dict(id="estr", group="short", label="€STR", kind="rate", freq="daily",
         source=ECB, fetch=(S.ecb, "EST", "B.EU000A2X2A25.WT")),
    dict(id="sofr", group="short", label="SOFR", kind="rate", freq="daily",
         source=FRED, fetch=(S.fred, "SOFR")),
    dict(id="euribor3m", group="short", label="Euribor 3M (moy. mensuelle)", kind="rate", freq="monthly",
         source=ECB, fetch=(S.ecb_monthly, "FM", "M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA"),
         note="Série quotidienne sous licence EMMI : seule la moyenne mensuelle est gratuite."),
    # ---------------------------------------------------------- Souverains
    dict(id="us2y", group="govt", label="US 2 ans", kind="rate", freq="daily", source=FRED, fetch=(S.fred, "DGS2")),
    dict(id="us10y", group="govt", label="US 10 ans", kind="rate", freq="daily", source=FRED, fetch=(S.fred, "DGS10")),
    dict(id="us30y", group="govt", label="US 30 ans", kind="rate", freq="daily", source=FRED, fetch=(S.fred, "DGS30")),
    dict(id="de2y", group="govt", label="Bund 2 ans", kind="rate", freq="daily", source=BBK,
         fetch=(S.bundesbank, "D.I.ZST.ZI.EUR.S1311.B.A604.R02XX.R.A.A._Z._Z.A"),
         note="Rendement issu de la courbe zéro-coupon estimée par la Bundesbank."),
    dict(id="de10y", group="govt", label="Bund 10 ans", kind="rate", freq="daily", source=BBK,
         fetch=(S.bundesbank, "D.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A"),
         note="Rendement issu de la courbe zéro-coupon estimée par la Bundesbank."),
    dict(id="fr10y_m", group="govt", label="OAT 10 ans (moy. mensuelle)", kind="rate", freq="monthly",
         source=ECB, fetch=(S.ecb_monthly, "IRS", "M.FR.L.L40.CI.0000.EUR.N.Z"),
         note="Pas de série quotidienne gratuite sans clé : taux long « de convergence » BCE."),
    dict(id="it10y_m", group="govt", label="BTP 10 ans (moy. mensuelle)", kind="rate", freq="monthly",
         source=ECB, fetch=(S.ecb_monthly, "IRS", "M.IT.L.L40.CI.0000.EUR.N.Z"),
         note="Pas de série quotidienne gratuite : taux long « de convergence » BCE."),
    dict(id="de10y_m", group="govt", label="Bund 10 ans (moy. mensuelle)", kind="rate", freq="monthly",
         source=ECB, fetch=(S.ecb_monthly, "IRS", "M.DE.L.L40.CI.0000.EUR.N.Z"), hidden=True),
    dict(id="gb10y", group="govt", label="Gilt 10 ans", kind="rate", freq="daily", source=BOE,
         fetch=(S.boe, "IUDMNPY"), note="Rendement au pair nominal 10 ans (BoE)."),
    dict(id="jp10y", group="govt", label="JGB 10 ans", kind="rate", freq="daily", source=MOF,
         fetch=(S.mof_jgb, "10Y")),
    # ---------------------------------------------------------- Spreads & pentes (calculés)
    dict(id="oat_bund", group="spreads", label="Spread OAT – Bund 10 ans (mensuel)", kind="rate",
         freq="monthly", source="Calcul (BCE)", derive=("sub", "fr10y_m", "de10y_m"), show_bp=True),
    dict(id="btp_bund", group="spreads", label="Spread BTP – Bund 10 ans (mensuel)", kind="rate",
         freq="monthly", source="Calcul (BCE)", derive=("sub", "it10y_m", "de10y_m"), show_bp=True),
    dict(id="us2s10s", group="spreads", label="Pente US 2s10s", kind="rate", freq="daily",
         source=FRED, fetch=(S.fred, "T10Y2Y"), show_bp=True),
    dict(id="de2s10s", group="spreads", label="Pente Allemagne 2s10s", kind="rate", freq="daily",
         source="Calcul (Bundesbank)", derive=("sub", "de10y", "de2y"), show_bp=True),
    # ---------------------------------------------------------- Anticipations
    dict(id="us_be10", group="expect", label="Point mort d'inflation US 10 ans", kind="rate", freq="daily",
         source=FRED, fetch=(S.fred, "T10YIE")),
    dict(id="us_proxy", group="expect", label="Proxy : US 2 ans – Fed (milieu)", kind="rate", freq="daily",
         source="Calcul (FRED)", derive=("sub_mid", "us2y", "fed_upper", "fed_lower"), show_bp=True,
         note="PROXY, pas une probabilité de marché : > 0 = le marché anticipe plutôt des hausses."),
    dict(id="eu_proxy", group="expect", label="Proxy : Bund 2 ans – taux de dépôt BCE", kind="rate",
         freq="daily", source="Calcul (Bundesbank, BCE)", derive=("sub", "de2y", "ecb_dfr"), show_bp=True,
         note="PROXY, pas une probabilité de marché : < 0 = le marché anticipe plutôt des baisses."),
    # ---------------------------------------------------------- Change
    dict(id="eurusd", group="fx", label="EUR/USD", kind="price", freq="daily", source=YAHOO, yahoo="EURUSD=X", dec=4),
    dict(id="usdjpy", group="fx", label="USD/JPY", kind="price", freq="daily", source=YAHOO, yahoo="JPY=X", dec=2),
    dict(id="gbpusd", group="fx", label="GBP/USD", kind="price", freq="daily", source=YAHOO, yahoo="GBPUSD=X", dec=4),
    dict(id="eurgbp", group="fx", label="EUR/GBP", kind="price", freq="daily", source=YAHOO, yahoo="EURGBP=X", dec=4),
    dict(id="usdchf", group="fx", label="USD/CHF", kind="price", freq="daily", source=YAHOO, yahoo="CHF=X", dec=4),
    dict(id="usdcny", group="fx", label="USD/CNY", kind="price", freq="daily", source=YAHOO, yahoo="CNY=X", dec=4),
    dict(id="dxy", group="fx", label="Dollar Index (DXY)", kind="price", freq="daily", source=YAHOO, yahoo="DX-Y.NYB", dec=2),
    # ---------------------------------------------------------- Actions
    dict(id="spx", group="equity", label="S&P 500", kind="price", freq="daily", source=YAHOO, yahoo="^GSPC"),
    dict(id="ndx", group="equity", label="Nasdaq 100", kind="price", freq="daily", source=YAHOO, yahoo="^NDX"),
    dict(id="sx5e", group="equity", label="Euro Stoxx 50", kind="price", freq="daily", source=YAHOO, yahoo="^STOXX50E"),
    dict(id="cac", group="equity", label="CAC 40", kind="price", freq="daily", source=YAHOO, yahoo="^FCHI"),
    dict(id="dax", group="equity", label="DAX", kind="price", freq="daily", source=YAHOO, yahoo="^GDAXI"),
    dict(id="ftse", group="equity", label="FTSE 100", kind="price", freq="daily", source=YAHOO, yahoo="^FTSE"),
    dict(id="nikkei", group="equity", label="Nikkei 225", kind="price", freq="daily", source=YAHOO, yahoo="^N225"),
    dict(id="hsi", group="equity", label="Hang Seng", kind="price", freq="daily", source=YAHOO, yahoo="^HSI"),
    dict(id="em", group="equity", label="MSCI EM (proxy ETF EEM, $)", kind="price", freq="daily", source=YAHOO,
         yahoo="EEM", dec=2, note="L'indice MSCI n'est pas diffusé gratuitement : ETF iShares EEM en proxy."),
    # ---------------------------------------------------------- Volatilité
    dict(id="vix", group="vol", label="VIX", kind="price", freq="daily", source=YAHOO, yahoo="^VIX", dec=2),
    dict(id="vstoxx", group="vol", label="VSTOXX", kind="price", freq="daily", source="—",
         na="Aucune source gratuite stable (ticker Yahoo retiré, données STOXX sous licence)."),
    dict(id="move", group="vol", label="MOVE (vol. taux US)", kind="price", freq="daily", source=YAHOO, yahoo="^MOVE", dec=2),
    # ---------------------------------------------------------- Crédit (licence ICE : variations seulement)
    dict(id="us_ig", group="credit", label="OAS Investment Grade US", kind="rate", freq="daily", source=FRED + " / ICE",
         fetch=(S.fred, "BAMLC0A0CM"), restricted=True),
    dict(id="us_hy", group="credit", label="OAS High Yield US", kind="rate", freq="daily", source=FRED + " / ICE",
         fetch=(S.fred, "BAMLH0A0HYM2"), restricted=True),
    dict(id="eu_ig", group="credit", label="OAS Investment Grade euro", kind="rate", freq="daily", source="—",
         na="Série non diffusée sur FRED ; iTraxx Main payant."),
    dict(id="eu_hy", group="credit", label="OAS High Yield euro", kind="rate", freq="daily", source=FRED + " / ICE",
         fetch=(S.fred, "BAMLHE00EHYIOAS"), restricted=True),
    # ---------------------------------------------------------- Matières premières & crypto
    dict(id="brent", group="commo", label="Brent ($/b)", kind="price", freq="daily", source=YAHOO, yahoo="BZ=F", dec=2),
    dict(id="wti", group="commo", label="WTI ($/b)", kind="price", freq="daily", source=YAHOO, yahoo="CL=F", dec=2),
    dict(id="ttf", group="commo", label="Gaz TTF (€/MWh)", kind="price", freq="daily", source=YAHOO, yahoo="TTF=F", dec=2),
    dict(id="gold", group="commo", label="Or ($/oz)", kind="price", freq="daily", source=YAHOO, yahoo="GC=F", dec=1),
    dict(id="silver", group="commo", label="Argent ($/oz)", kind="price", freq="daily", source=YAHOO, yahoo="SI=F", dec=2),
    dict(id="copper", group="commo", label="Cuivre ($/lb)", kind="price", freq="daily", source=YAHOO, yahoo="HG=F", dec=3),
    dict(id="btc", group="commo", label="Bitcoin ($)", kind="price", freq="daily", source=YAHOO, yahoo="BTC-USD", dec=0),
    # ---------------------------------------------------------- Macro (dernière publication + précédente)
    dict(id="us_cpi", group="macro", label="CPI US (a/a)", kind="macro", freq="monthly", source=FRED,
         fetch=(S.fred, "CPIAUCSL", 900), transform="yoy", unit="%"),
    dict(id="us_core_cpi", group="macro", label="CPI US core (a/a)", kind="macro", freq="monthly", source=FRED,
         fetch=(S.fred, "CPILFESL", 900), transform="yoy", unit="%"),
    dict(id="us_core_pce", group="macro", label="PCE core US (a/a)", kind="macro", freq="monthly", source=FRED,
         fetch=(S.fred, "PCEPILFE", 900), transform="yoy", unit="%"),
    dict(id="ea_hicp", group="macro", label="HICP zone euro (a/a)", kind="macro", freq="monthly", source=ESTAT,
         fetch=(S.eurostat, "prc_hicp_minr", {"coicop18": "TOTAL", "unit": "RCH_A"}), unit="%"),
    dict(id="ea_core", group="macro", label="HICP core zone euro (a/a)", kind="macro", freq="monthly", source=ESTAT,
         fetch=(S.eurostat, "prc_hicp_minr", {"coicop18": "TOT_X_NRG_FOOD", "unit": "RCH_A"}), unit="%",
         note="Hors énergie et alimentation."),
    dict(id="fr_hicp", group="macro", label="Inflation France – IPCH (a/a)", kind="macro", freq="monthly",
         source=ESTAT, fetch=(S.eurostat, "prc_hicp_minr", {"coicop18": "TOTAL", "unit": "RCH_A"}, ("FR",)),
         unit="%", note="Indice harmonisé (IPCH), celui que suit la BCE."),
    dict(id="nfp", group="macro", label="NFP US (créations, milliers)", kind="macro", freq="monthly", source=FRED,
         fetch=(S.fred, "PAYEMS", 900), transform="mom_diff", unit="k", dec=0),
    dict(id="us_unemp", group="macro", label="Chômage US", kind="macro", freq="monthly", source=FRED,
         fetch=(S.fred, "UNRATE", 900), unit="%"),
    dict(id="ea_unemp", group="macro", label="Chômage zone euro", kind="macro", freq="monthly", source=ESTAT,
         fetch=(S.eurostat, "une_rt_m", {"s_adj": "SA", "age": "TOTAL", "sex": "T", "unit": "PC_ACT"}), unit="%"),
    dict(id="us_gdp", group="macro", label="PIB US (t/t annualisé)", kind="macro", freq="quarterly", source=FRED,
         fetch=(S.fred, "A191RL1Q225SBEA", 900), unit="%"),
    dict(id="ea_gdp", group="macro", label="PIB zone euro (t/t)", kind="macro", freq="quarterly", source=ESTAT,
         fetch=(S.eurostat, "namq_10_gdp", {"s_adj": "SCA", "na_item": "B1GQ", "unit": "CLV_PCH_PRE", "_freq": "Q"}),
         unit="%"),
    dict(id="cn_gdp", group="macro", label="PIB Chine", kind="macro", freq="quarterly", source="—",
         na="Pas d'API gratuite à jour (la série OCDE sur FRED s'arrête en 2023)."),
    dict(id="pmi", group="macro", label="PMI composites", kind="macro", freq="monthly", source="—",
         na="Données propriétaires S&P Global / HCOB, non redistribuables gratuitement."),
]

BY_ID = {s["id"]: s for s in SERIES}
