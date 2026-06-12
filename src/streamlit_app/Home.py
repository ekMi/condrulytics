from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).parent
LOGO_PATH = APP_DIR / "pictures" / "logo.png"


st.set_page_config(
    page_title="CondruLytics",
    layout="wide",
)

left, right = st.columns([3, 1])

with left:
    st.title("CondruLytics")
    st.write(
        "CondruLytics permet d'explorer les résultats du Challenge Condrusien : "
        "suivi des performances, comparaison des courses et analyse de l'évolution "
        "des coureurs au fil des éditions."
    )

with right:
    st.image(LOGO_PATH, use_container_width=True)

st.divider()

st.subheader("Que peut-on faire dans l'application ?")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**Vue d'ensemble**")
    st.write("Observer la participation, les courses et les tendances par année.")

with col2:
    st.markdown("**Courses**")
    st.write("Consulter les classements, les temps, les vitesses et les allures.")

with col3:
    st.markdown("**Coureurs**")
    st.write("Suivre l'historique et l'évolution des performances individuelles.")

st.subheader("Comment lire l'indice de performance ?")
st.info(
    "L'indice compare une performance aux autres coureurs de la même course. "
    "100 correspond à une performance proche de la moyenne de cette course. "
    "Au-dessus de 100, le coureur a été plus rapide que la moyenne ; en dessous "
    "de 100, il a été moins rapide. Par exemple, 103 signifie légèrement au-dessus "
    "de la moyenne, pas une note sur 100."
)
st.caption(
    "Cet indice sert surtout à comparer l'évolution d'un coureur entre des courses "
    "de distances différentes. Il reste influencé par le niveau des participants "
    "présents sur chaque course."
)

st.warning(
    "Mise en garde : les analyses dépendent des données sources. "
    "Des erreurs peuvent subsister, notamment à cause de noms mal orthographiés, "
    "de doublons, de chronos manquants ou de formats de classement différents "
    "selon les éditions."
)
