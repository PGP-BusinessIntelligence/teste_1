import streamlit as st
import pandas as pd
import numpy as np
import requests
import openpyxl
import re
from datetime import datetime
from zoneinfo import ZoneInfo

# Importando funções e dados
import refresh_dataset as rd
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


token = rd.get_token()

headers = {'Authorization':f'Bearer {token}',
'Content-Type': 'application/json',}

requisicao_groupos = requests.get("https://api.powerbi.com/v1.0/myorg/groups", headers=headers)

grupro_requisicao = requisicao_groupos.json()['value']

pd_groupos = pd.json_normalize(grupro_requisicao)
pd_grupos = pd_groupos[['id','name']]
pd_grupos = pd_grupos.rename(columns={'name':'nome_workspace','id':'id_workspace'})

pd_dataset_final = pd.DataFrame()
for grupo, nome_grupo in zip(pd_grupos['id_workspace'], pd_grupos['nome_workspace']):
    datasets = requests.get(f"https://api.powerbi.com/v1.0/myorg/groups/{grupo}/datasets", headers=headers)
    datasets_requisicao = datasets.json()['value']
    pd_datasets = pd.json_normalize(datasets_requisicao)
    pd_dataset = pd_datasets[["id","name","createdDate","configuredBy","isRefreshable","isOnPremGatewayRequired"]]
    pd_dataset = pd_dataset.rename(columns={'id':'dataset_id_modelo_semantico','name':'nome_modelo_semantico','createdDate':'data_criacao_modelo_semantico','configuredBy':'configurado_por_modelo_semantico','isRefreshable':'atualizacao_automatica_modelo_semantico','isOnPremGatewayRequired':'requer_gatway_modelo_semantico'})
    pd_dataset["id_workspace"] = grupo
    pd_dataset["nome_workspace"] = nome_grupo

    # concatena no DataFrame final
    pd_dataset_final = pd.concat([pd_dataset_final, pd_dataset], ignore_index=True)

pd_refreshSchedule_final = pd.DataFrame()

for grupo in pd_dataset_final['id_workspace'].unique():
    pd_refreshSchedule_quase_final = pd.DataFrame()

    # pega apenas os datasets daquele grupo
    datasets_grupo = pd_dataset_final[pd_dataset_final['id_workspace'] == grupo]

    for dataset in datasets_grupo['dataset_id_modelo_semantico']:
        refreshSchedules = requests.get(
            f"https://api.powerbi.com/v1.0/myorg/groups/{grupo}/datasets/{dataset}/refreshSchedule",
            headers=headers
        )

        if refreshSchedules.status_code == 200:
            refreshSchedules_requisicao = refreshSchedules.json()
            pd_refreshSchedules = pd.json_normalize(refreshSchedules_requisicao)

            # remove a duplicada "localTimeZoneId"
            pd_refreshSchedule = pd_refreshSchedules[["days","times","localTimeZoneId","enabled"]]
            pd_refreshSchedule = pd_refreshSchedule.rename(columns={'days':'dias','times':'horarios','enabled':'habilitado'})
            pd_refreshSchedule['dataset_id_modelo_semantico'] = dataset

            pd_refreshSchedule_quase_final = pd.concat(
                [pd_refreshSchedule_quase_final, pd_refreshSchedule],
                ignore_index=True
            )

    pd_refreshSchedule_final = pd.concat(
        [pd_refreshSchedule_final, pd_refreshSchedule_quase_final],
        ignore_index=True
    )

df_quase_final = pd.merge(
    pd_dataset_final,
    pd_refreshSchedule_final,
    on="dataset_id_modelo_semantico",
    how="left"  # mantém todos os datasets, mesmo os sem agendamento
)

pd_refreshes_final = pd.DataFrame()

for data_set_id, grup_id in zip(df_quase_final['dataset_id_modelo_semantico'], df_quase_final['id_workspace']):
    refreshes = requests.get(
        f"https://api.powerbi.com/v1.0/myorg/groups/{grup_id}/datasets/{data_set_id}/refreshes",
        headers=headers
    )
    refreshes_requisicao = refreshes.json().get('value', [])
    
    if not refreshes_requisicao:  # se vier vazio, pula
        continue
    
    pd_refreshes = pd.json_normalize(refreshes_requisicao)
    
    # só mantém colunas que realmente existem
    colunas_desejadas = ["requestId", "id", "refreshType", "startTime", "endTime", "status"]
    colunas_existentes = [c for c in colunas_desejadas if c in pd_refreshes.columns]
    
    pd_refreshe = pd_refreshes[colunas_existentes].copy()
    pd_refreshe["dataset_id_modelo_semantico"] = data_set_id
       
    pd_refreshes_final = pd.concat([pd_refreshes_final, pd_refreshe], ignore_index=True)

pd_refreshes_final = pd_refreshes_final.rename(columns={'requestId':'requestId_atualizacao', 'id':'id_atualizacao','startTime':'startTime_atualizacao', 'endTime':'endTime_atualizacao', 'status':'status_atualizacao'})

#pd_refreshes_final
df_q_final = pd.merge(
    pd_refreshes_final,
    df_quase_final,
    on="dataset_id_modelo_semantico",
    how="left"  # mantém todos os datasets, mesmo os sem agendamento
)

pd_reports_final = pd.DataFrame()
for idgrupo in pd_grupos['id_workspace'] :
    reports = requests.get(f"https://api.powerbi.com/v1.0/myorg/groups/{idgrupo}/reports", headers=headers)
    reports_requisicao = reports.json().get('value', [])

    if not reports_requisicao:
        continue

    pd_reports = pd.json_normalize(reports_requisicao)

    colunas_esperadas = ["reportType","name", "datasetId","datasetWorkspaceId"]
    colunas__Existentes = [coluna for coluna in colunas_esperadas if coluna in pd_reports.columns]

    pd_report = pd_reports[colunas__Existentes].copy()
    pd_report = pd_report.rename(columns={'datasetId':'dataset_id_modelo_semantico','name':'nome_dashboard'})

    pd_reports_final = pd.concat([pd_reports_final,pd_report], ignore_index=True)

#pd_reports_final
df_final = pd.merge(
    pd_reports_final,
    df_q_final,
    on="dataset_id_modelo_semantico",
    how="left"
)

valores_remover = ["Microsoft 365 Usage Analytics", "PaginatedReport"]

# remove valores indesejados só se a coluna existir
for col in ["reportType", "nome_dashboard"]:
    if col in df_final.columns:
        df_final = df_final[~df_final[col].isin(valores_remover)]

# transforma em caixa alta apenas colunas de texto
colunas_alvo = [
    "reportType", "nome_dashboard", "refreshType",
    "status_atualizacao", "nome_modelo_semantico",
    "nome_workspace","configurado_por_modelo_semantico"
]

for col in colunas_alvo:
    if col in df_final.columns and df_final[col].dtype == "object":
        df_final[col] = df_final[col].str.upper()

# traduz os dias para português
dias_ptbr = {
    'Sunday':'DOMINGO', 
    'Monday':'SEGUNDA-FEIRA', 
    'Tuesday':'TERÇA-FEIRA', 
    'Wednesday':'QUARTA-FEIRA', 
    'Thursday':'QUINTA-FEIRA', 
    'Friday':'SEXTA-FEIRA', 
    'Saturday':'SÁBADO'
}

if "dias" in df_final.columns:
    df_final["dias"] = df_final["dias"].astype(str)  # garante string
    for eng, pt in dias_ptbr.items():
        df_final["dias"] = df_final["dias"].str.replace(eng, pt, regex=False)

    # caso a célula tenha todos os dias de uma vez só
    df_final["dias"] = df_final["dias"].replace(
        {"[DOMINGO, SEGUNDA-FEIRA, TERÇA-FEIRA, QUARTA-FEIRA, QUINTA-FEIRA, SEXTA-FEIRA, SÁBADO]": "TODOS OS DIAS"}
    )
# lista de todos os dias em PT-BR
todos_dias = [
    "DOMINGO", "SEGUNDA-FEIRA", "TERÇA-FEIRA", 
    "QUARTA-FEIRA", "QUINTA-FEIRA", "SEXTA-FEIRA", "SÁBADO"
]

def normalizar_dias(valor):
    # garante string
    valor_str = str(valor)
    
    # se contém todos os dias → retorna "TODOS OS DIAS"
    if all(dia in valor_str for dia in todos_dias):
        return "TODOS OS DIAS"
    
    # caso contrário, retorna o valor original (já traduzido)
    return valor_str

if "dias" in df_final.columns:
    df_final["dias"] = df_final["dias"].apply(normalizar_dias)

def limpar_dias(valor):
    valor_str = str(valor)

    valor_str = re.sub(r"[\[\]']","", valor_str)

    valor_str = valor_str.strip()

    return valor_str

df_final["dias"] = df_final["dias"].apply(limpar_dias)
df_final["horarios"] = df_final["horarios"].apply(limpar_dias)
# df_final["data_criacao_modelo_semantico"] = pd.to_datetime(df_final["data_criacao_modelo_semantico"])
# df_final["data_criacao_modelo_semantico"] = df_final["data_criacao_modelo_semantico"].dt.date
#df_final.to_excel("teste1.xlsx", index=False)

# df_final["data_criacao_modelo_semantico"] = pd.to_datetime(df_final["data_criacao_modelo_semantico"], utc=True)
# df_final["data_criacao_modelo_semantico"] = (df_final["data_criacao_modelo_semantico"].dt.tz_convert("America/Sao_Paulo"))

colunas_datas = ["data_criacao_modelo_semantico","startTime_atualizacao","endTime_atualizacao"]

for col in colunas_datas:
    df_final[col] = pd.to_datetime(df_final[col], utc=True, errors="coerce").dt.tz_convert("America/Sao_Paulo")

contagem = df_final['dataset_id_modelo_semantico'].nunique()

filtro = ["SCHEDULED", "VIAAPI", "DIRECTLAKEFRAMING"]

df_final_filtrado = df_final.loc[df_final["refreshType"].isin(filtro)].copy()
df_final_filtrado["endTime_atualizacao"] = pd.to_datetime(df_final_filtrado["endTime_atualizacao"], errors="coerce")

# 🔹 remove linhas sem data
df_final_filtrado = df_final_filtrado.dropna(subset=["endTime_atualizacao"])

# 🔹 agora sim pega só a mais recente de cada dataset
ultimas = (
    df_final_filtrado.sort_values("endTime_atualizacao", ascending=False)
    .groupby("nome_dashboard")
    .head(1)  # ou tail(1), mas como já ordenou decrescente, head(1) é mais direto
    .reset_index(drop=True)
)

filtragem_para_contar_dash = (
    df_final_filtrado.sort_values("endTime_atualizacao", ascending=False)
    .groupby("nome_dashboard")
    .head(1)  # ou tail(1), mas como já ordenou decrescente, head(1) é mais direto
    .reset_index(drop=True)
)

tabela = ultimas[["nome_dashboard","nome_modelo_semantico", "status_atualizacao", "endTime_atualizacao", "refreshType", "dias"]].copy()
tabela["endTime_atualizacao"] = tabela["endTime_atualizacao"].dt.strftime("%Y-%m-%d %H:%M")
tabelaordenada = tabela.sort_values("status_atualizacao",
                                     ascending=False).reset_index(drop=True).rename(columns={'nome_modelo_semantico':'Modelo Semantico',
                                                                                             'nome_dashboard':'Dashboard', 'status_atualizacao': 'Status', 'atualização': 'Dias de Atualização',
                                                                                             'endTime_atualizacao': 'Última atualização','refreshType': 'Tipo', 'dias':'Periodicidade de Atualização' })


qtd_dash = tabelaordenada['Dashboard'].nunique()
qtd_semantico = tabelaordenada['Modelo Semantico'].nunique()
contagem_erros = (tabelaordenada["Status"] == "FAILED").sum()

filtro2 = ["FAILED"]

tabelaordenada  = tabelaordenada.loc[tabelaordenada ["Status"].isin(filtro2)].copy()
print(tabelaordenada)