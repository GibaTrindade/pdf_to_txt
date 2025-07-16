from django.shortcuts import render
from .forms import PDFUploadForm
import pdfplumber
import re
import unicodedata

# Dicionário padrão com nome no PDF → sigla
SUBSTANCIAS_PADRAO = {
    "HEMOGLOBINA": "HB",
    "HEMATÓCRITO": "HT",
    "VCM": "VCM",
    "HCM": "HCM",
    "RDW": "RDW",
    "LEUCÓCITOS": "LEUCO",
    "SEGMENTADOS": "SEG",
    "LINFÓCITOSTÍPICOS": "LT",
    "LINFÓCITOSATÍPICOS": "LA",
    "EOSINÓFILOS": "EOS",
    "MONÓCITOS": "MONO",
    "PLAQUETAS": "PLAQ",
    "UREIA": "UR",
    "CREATININA": "CR",
    "SODIO": "NA",
    "POTASSIO": "K",
    "TGO": "TGO",
    "TRANSAMINASE GLUTAMICO-OXALACETICA": "TGO",
    "TGP": "TGP",
    "ALANINA AMINOTRANSFERASE": "TGP",
    "BILIRRUBINA TOTAL": "BT",
    "DIRETA": "BD",
    "INDIRETA": "BI",
    "COLESTEROL TOTAL": "COL-T",
    "COLESTEROL HDL": "HDL",
    "COLESTEROL LDL": "LDL",
    "TRIGLICERIDEOS": "TG",
    #"HEMOGLOBINA GLICADA": "HbA1c",
    "GLICOSE MÉDIA ESTIMADA": "GME",
    #"ALBUMINA SERICA": "ALB",
    #"HEMOGLOBINA GLICADA": "HbA1c",
    "HEMOGLOBINAGLICADA-HBA1C": "HbA1c",
    "ALBUMINASERICA": "ALB",
    "DOSAGEMDECOLESTEROLLDL": "LDL",
    "DOSAGEMDECOLESTEROLHDL": "HDL",
    "COLESTEROLTOTAL": "COL-T",
}

def remover_acentos(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def extrair_data_coleta(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        texto = "\n".join(p.extract_text() for p in pdf.pages if p.extract_text())

    texto = remover_acentos(texto).lower().replace(" ", "")  # remove acentos e espaços

    # Procurar qualquer padrão tipo 'coletadoem11/07/2025'
    match = re.search(r'coletadoem(\d{2}/\d{2}/\d{4})', texto)
    if match:
        data_completa = match.group(1)
        return "/".join(data_completa.split("/")[:2])  # retorna 11/07
    return None

def extrair_resultados(pdf):
    with pdfplumber.open(pdf) as pdf_obj:
        texto = ""
        for pagina in pdf_obj.pages:
            texto += pagina.extract_text()

    texto = texto.replace(",", ".").replace("\n", " ")
    texto_limpo = remover_acentos(texto).upper()

    resultados = {}
    encontrados = set()

    for nome_completo, sigla in SUBSTANCIAS_PADRAO.items():
        nome_base = remover_acentos(nome_completo).upper()

        # Busca 1: Nome + valor direto (ex: TGO: 17)
        match = re.search(rf"{re.escape(nome_base)}[.:·\s]*([\d.]+)", texto_limpo)
        if match:
            resultados[sigla] = match.group(1)
            encontrados.add(sigla)
            continue

        # Busca 2: Nome + Resultado: valor (linha próxima)
        match = re.search(rf"{re.escape(nome_base)}.*?RESULTADO[.:·\-\s]*([\d.]+)", texto_limpo)
        if match:
            resultados[sigla] = match.group(1)
            encontrados.add(sigla)
            continue

        # Busca 3: fallback — Resultado perto de nome
        pattern_fallback = rf"{re.escape(nome_base)}.*?RESULTADO[^\d]*([\d.]+)"
        match = re.search(pattern_fallback, texto_limpo)
        if match and sigla not in resultados:
            resultados[sigla] = match.group(1)
            encontrados.add(sigla)

    # Extras fora da lista
    extras_raw = re.findall(r"([A-ZÇÃÕÂÊÁÉÍÓÚÀÜ ]{3,})[.:·\s]*([\d.]+)", texto_limpo)
    extras_filtrados = [
        {"nome": nome.strip(), "valor": valor}
        for nome, valor in extras_raw
        if nome.strip() not in SUBSTANCIAS_PADRAO and nome.strip() not in encontrados
    ]

    return resultados, extras_filtrados

def upload_view(request):
    resultados_por_arquivo = []

    if request.method == 'POST':
        arquivos = request.FILES.getlist('arquivos')
        for arquivo in arquivos:
            resultados, extras = extrair_resultados(arquivo)
            data_coleta = extrair_data_coleta(arquivo) or "??/??"

            # Ordem desejada no output
            siglas_ordenadas = [
                "HB", "HT", "VCM", "HCM", "RDW",
                "LEUCO", "SEG", "LT", "LA", "EOS", "MONO", "PLAQ",
                "UR", "CR", "NA", "K",
                "TGO", "TGP", "BT", "BD", "BI",
                "COL-T", "HDL", "LDL", "TG",
                "HbA1c", "GME", "ALB"
            ]

            blocos = []
            for sigla in siglas_ordenadas:
                valor = resultados.get(sigla)
                if valor:
                    blocos.append(f"{sigla}: {valor}")

            texto_formatado = f"- LAB ({data_coleta}): " + " | ".join(blocos)

            resultados_por_arquivo.append({
                "nome": arquivo.name,
                "resultados": resultados,
                "extras": extras,
                "texto_formatado": texto_formatado
            })

    form = PDFUploadForm()
    return render(request, 'laboratorio/upload.html', {
        'form': form,
        'resultados_por_arquivo': resultados_por_arquivo
    })
