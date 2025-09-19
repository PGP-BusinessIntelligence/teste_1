import streamlit as st
import pandas as pd
import numpy as np
import requests
import re
from datetime import datetime
from zoneinfo import ZoneInfo

# Importando funções e dados
import refresh_dataset as rd
from dataframe import tabelaordenada, qtd_dash, contagem_erros,qtd_semantico

# AgGrid e SlickGrid
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from streamlit_slickgrid import (
    add_tree_info,
    slickgrid,
    Formatters,
    Filters,
    FieldType,
    OperatorType,
    ExportServices,
    StreamlitSlickGridFormatters,
    StreamlitSlickGridSorters,
)

st.set_page_config(layout="wide")
# -------------------------------
# Título do app
# -------------------------------
cols1 = st.columns([1, 10])  # 1 para a imagem, 10 para o título

with cols1[0]:
    st.image("logo_pgp.jpeg", width=120)

with cols1[1]:
    st.title("Controle de Atualizações - PowerBi")

# -------------------------------
# Carregar DataFrame
# -------------------------------
df = tabelaordenada.reset_index(drop=True)
df["id"] = df.index.astype(str)

@st.cache_data()
def load_data():
    return df

data = load_data()

# -------------------------------
# Métricas
# -------------------------------
cols = st.columns(3)
with cols[0]:
    st.metric(label="Qtd - Total Dashboard", value=qtd_dash, border=True)
with cols[1]:
    st.metric(label="Qtd - Modelos Semânticos", value=qtd_semantico, border=True)
with cols[2]:
    st.metric(label="Qtd - Erros", value=contagem_erros, border=True)

# -------------------------------
# Converter para registros
# -------------------------------
records = data.to_dict(orient="records")

# -------------------------------
# Criar árvore 3 níveis manualmente
# -------------------------------
tree_records = []

for rec in records:
    # Nível 0: Status (pai)
    status_id = f"status_{rec['Status']}"
    if not any(d.get("id") == status_id for d in tree_records):
        tree_records.append({
            "id": status_id,
            "title": rec["Status"],
            "__parent": None,
            "__depth": 0,
            "Última atualização": None,
            "Tipo": None,
            "Periodicidade de Atualização": None,
            "__collapsed": False  # 👈 pai começa aberto
        })
    
    # Nível 1: Modelo Semantico (filho do Status)
    modelo_id = f"modelo_{rec['Status']}_{rec['Modelo Semantico']}"
    if not any(d.get("id") == modelo_id for d in tree_records):
        tree_records.append({
            "id": modelo_id,
            "title": rec["Modelo Semantico"],
            "__parent": status_id,
            "__depth": 1,
            "Última atualização": rec["Última atualização"],
            "Tipo": rec["Tipo"],
            "Periodicidade de Atualização": rec["Periodicidade de Atualização"],
            "__collapsed": True   # 👈 filhos começam fechados
        })
    
    # Nível 2: Dashboard (filho do Modelo)
    dash_id = rec["id"]
    tree_records.append({
        "id": dash_id,
        "title": rec["Dashboard"],
        "__parent": modelo_id,
        "__depth": 2,
        "Última atualização": rec["Última atualização"],
        "Tipo": rec["Tipo"],
        "Periodicidade de Atualização": rec["Periodicidade de Atualização"],
        "__collapsed": True   # 👈 netos também fechados
    })

# -------------------------------
# Colunas do grid
# -------------------------------
columns = [
    {
        "id": "title",
        "name": "Title",
        "field": "title",
        "sortable": True,
        "minWidth": 300,
        "type": FieldType.string,
        "filterable": True,
        "formatter": Formatters.tree,
        "exportCustomFormatter": Formatters.treeExport,
    },
    {
        "id": "Última atualização",
        "name": "Última atualização",
        "field": "Última atualização",
        "sortable": True,
        "minWidth": 150,
        "type": FieldType.dateTime,
        "filterable": True,
        "formatter": Formatters.dateTimeShortIso,
    },
    {
        "id": "Tipo",
        "name": "Tipo",
        "field": "Tipo",
        "sortable": True,
        "minWidth": 150,
        "type": FieldType.string,
        "filterable": True,
    },
    {
        "id": "Periodicidade de Atualização",
        "name": "Periodicidade de Atualização",
        "field": "Periodicidade de Atualização",
        "sortable": True,
        "minWidth": 150,
        "type": FieldType.string,
        "filterable": True,
    },
]

# -------------------------------
# Opções do grid
# -------------------------------
options = {
    "enableFiltering": True,
    "enableTextExport": True,
    "enableExcelExport": True,
    "externalResources": [ExportServices.ExcelExportService, ExportServices.TextExportService],
    "enableAutoResize": True,
    "autoResize": {
        "minHeight": 400,
        "maxHeight": 800   # força altura fixa
    },
    "enableTreeData": True,
    "multiColumnSort": False,
    "treeDataOptions": {
        "columnId": "title",           # coluna usada para exibir árvore
        "indentMarginLeft": 15,        # recuo de cada nível
       # "initiallyCollapsed": lambda item: item["__depth"] > 0,  # abre só o nível 0
        "parentPropName": "__parent",  # campo do pai
        "levelPropName": "__depth",    # nível do item
    },
}

# -------------------------------
# Renderiza a árvore
# -------------------------------
out = slickgrid(tree_records, columns, options, key="mygrid", on_click="rerun")
