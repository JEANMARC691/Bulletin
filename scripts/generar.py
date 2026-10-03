#!/usr/bin/env python3
"""Genera la edición semanal del Bulletin Rilamax (francés + español).

1. Claude investiga la semana con búsqueda web y redacta la edición francesa (JSON).
2. Claude adapta la edición al español (JSON), sin nuevas búsquedas.
3. Se generan las páginas HTML del sitio y los textos para LinkedIn.
"""
import datetime
import json
import os
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

import anthropic
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE, OUT, DATA = ROOT / "site", ROOT / "out", ROOT / "data"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
MODELO = os.environ.get("BULLETIN_MODEL") or CONFIG["modelo"]
SITE_URL = CONFIG["site_url"].rstrip("/")
TZ = ZoneInfo("Europe/Madrid")

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

LABELS = {
    "fr": {
        "titulo": "Le Bulletin Rilamax", "p1": "France", "p2": "Espagne",
        "numero": "N° {n} · Semaine {s}", "lectura": "Lecture : {m} minutes",
        "toc_aria": "Sommaire", "lang_aria": "Langue",
        "edito": "L'édito", "cifras": "Les chiffres", "cifras_t": "Les chiffres de la semaine",
        "dossier": "Le dossier", "dossier_pref": "Le dossier : ",
        "agenda": "À surveiller", "agenda_t": "À surveiller dans les prochaines semaines",
        "puntos": "Les trois points à retenir", "lectura_r": "Lecture Rilamax",
        "debate": "Le débat", "vigilaremos": "Ce que nous surveillerons",
        "fuentes": "Sources : ", "fuente": "Source : ", "archivo": "Éditions précédentes",
        "todas": "Toutes les éditions", "ultima": "Dernière édition",
        "glosario": "Lexique", "glosario_t": "Les sigles de cette édition",
        "firma": "— Jean Marc, RILAMAX 2025",
        "cta": "Le Bulletin Rilamax paraît chaque samedi : l'essentiel de l'économie, de la finance et de la politique entre la France et l'Espagne, avec notre lecture.",
        "cta_btn": "S'abonner sur LinkedIn",
        "footer": "Le Bulletin Rilamax est publié par RILAMAX 2025 SL. Les résumés sont rédigés par nos soins à partir des sources citées. Les lectures Rilamax sont des analyses générales et ne constituent pas des conseils d'investissement personnalisés.",
    },
    "es": {
        "titulo": "El Boletín Rilamax", "p1": "Francia", "p2": "España",
        "numero": "N.º {n} · Semana {s}", "lectura": "Lectura: {m} minutos",
        "toc_aria": "Sumario", "lang_aria": "Idioma",
        "edito": "El editorial", "cifras": "Las cifras", "cifras_t": "Las cifras de la semana",
        "dossier": "El dossier", "dossier_pref": "El dossier: ",
        "agenda": "A vigilar", "agenda_t": "A vigilar en las próximas semanas",
        "puntos": "Los tres puntos clave", "lectura_r": "Lectura Rilamax",
        "debate": "El debate", "vigilaremos": "Lo que vigilaremos",
        "fuentes": "Fuentes: ", "fuente": "Fuente: ", "archivo": "Ediciones anteriores",
        "todas": "Todas las ediciones", "ultima": "Última edición",
        "glosario": "Glosario", "glosario_t": "Las siglas de esta edición",
        "firma": "— Jean Marc, RILAMAX 2025",
        "cta": "El Boletín Rilamax se publica cada sábado: lo esencial de la economía, las finanzas y la política entre Francia y España, con nuestra lectura.",
        "cta_btn": "Suscribirse en LinkedIn",
        "footer": "El Boletín Rilamax lo publica RILAMAX 2025 SL. Los resúmenes son de elaboración propia a partir de las fuentes citadas. Las lecturas Rilamax son análisis generales y no constituyen asesoramiento de inversión personalizado.",
    },
}

USO = {"input": 0, "output": 0, "busquedas": 0}


def log(msg):
    print(f"[bulletin] {msg}", flush=True)


# ---------------------------------------------------------------- Claude
def llamar_claude(system, user, buscar):
    client = anthropic.Anthropic(max_retries=4, timeout=1800)
    messages = [{"role": "user", "content": user}]
    kwargs = {"model": MODELO, "max_tokens": 32000, "system": system}
    if buscar:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search",
                            "max_uses": int(CONFIG.get("max_busquedas", 30))}]
    textos = []
    cortes = 0
    for _ in range(16):
        with client.messages.stream(messages=messages, **kwargs) as stream:
            msg = stream.get_final_message()
        u = msg.usage
        USO["input"] += u.input_tokens or 0
        USO["output"] += u.output_tokens or 0
        stu = getattr(u, "server_tool_use", None)
        if stu is not None:
            USO["busquedas"] += getattr(stu, "web_search_requests", 0) or 0
        textos += [b.text for b in msg.content if b.type == "text"]
        if msg.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": msg.content})
            continue
        if msg.stop_reason == "max_tokens":
            cortes += 1
            if cortes > 3:
                raise RuntimeError("La respuesta de Claude se cortó por longitud varias veces seguidas (max_tokens).")
            log(f"Respuesta cortada por longitud; se pide continuar ({cortes}).")
            messages.append({"role": "assistant", "content": msg.content})
            messages.append({"role": "user", "content": (
                "Tu respuesta se ha cortado por longitud. Continúa exactamente desde el último carácter que escribiste, "
                "sin repetir nada, sin abrir de nuevo la etiqueta <json> y sin añadir comentarios.")})
            continue
        break
    return "".join(textos)


def extraer_json(texto):
    m = re.search(r"<json>\s*(.*?)\s*</json>", texto, re.S)
    cand = m.group(1) if m else texto[texto.find("{"): texto.rfind("}") + 1]
    cand = re.sub(r"^```(?:json)?\s*|\s*```$", "", cand.strip())
    return json.loads(cand)


def obtener_edicion(system, user, buscar):
    texto = llamar_claude(system, user, buscar)
    try:
        return extraer_json(texto)
    except Exception as err:  # noqa: BLE001
        log(f"JSON no válido ({err}); se pide una corrección.")
        arreglo = llamar_claude(
            system,
            "El texto siguiente debía ser un JSON válido con el esquema indicado, pero no lo es. "
            "Devuelve únicamente el JSON corregido, completo, entre <json> y </json>, sin cambiar el contenido.\n\n"
            + texto[-120000:],
            False,
        )
        return extraer_json(arreglo)


# ---------------------------------------------------------------- Validación
def validar(ed, idioma):
    faltan = [k for k in ("editorial", "cifras", "dossier", "francia", "espana", "agenda", "linkedin") if not ed.get(k)]
    if faltan:
        raise ValueError(f"Edición {idioma}: faltan apartados {faltan}")
    d = ed["dossier"]
    for k in ("titulo", "intro", "secciones", "lectura"):
        if not d.get(k):
            raise ValueError(f"Edición {idioma}: el dossier no tiene «{k}»")
    ed["glosario"] = sorted([g for g in (ed.get("glosario") or []) if g.get("sigla") and g.get("definicion")],
                            key=lambda g: g["sigla"].lower())
    d.setdefault("cifras", [])
    d.setdefault("graficos", [])
    d.setdefault("fuentes", [])
    d["graficos"] = [g for g in (d.get("graficos") or []) if g and g.get("barras")]
    for g in d["graficos"]:
        g["despues_de_seccion"] = int(g.get("despues_de_seccion") or 1)
        maximo = max(float(b.get("valor") or 0) for b in g["barras"]) or 1
        for b in g["barras"]:
            b["pct"] = min(100, max(1, round(float(b.get("valor") or 0) / maximo * 100)))
    if d.get("debate") and d["debate"].get("texto"):
        d["debate"]["despues_de_seccion"] = int(d["debate"].get("despues_de_seccion") or 1)
    else:
        d["debate"] = None
    for c in ed["cifras"]:
        c["pais"] = "es" if str(c.get("pais", "")).lower().startswith("es") else "fr"
    visibles = {k: v for k, v in ed.items() if k not in ("linkedin", "minutos")}
    texto = json.dumps(visibles, ensure_ascii=False)
    texto = re.sub(r'"(url|fuentes|fuente|pais|aria|despues_de_seccion|valor|pct)"\s*:\s*("[^"]*"|\d+|\[[^\]]*\])', " ", texto)
    palabras = len(re.findall(r"\w+", texto))
    ed["minutos"] = max(5, round(palabras / 230))
    return ed


# ---------------------------------------------------------------- Fechas
def rango(lunes, sabado, idioma):
    m = MOIS if idioma == "fr" else MESES
    if idioma == "fr":
        if lunes.month == sabado.month:
            return f"Du {lunes.day} au {sabado.day} {m[sabado.month - 1]} {sabado.year}"
        return f"Du {lunes.day} {m[lunes.month - 1]} au {sabado.day} {m[sabado.month - 1]} {sabado.year}"
    if lunes.month == sabado.month:
        return f"Del {lunes.day} al {sabado.day} de {m[sabado.month - 1]} de {sabado.year}"
    return f"Del {lunes.day} de {m[lunes.month - 1]} al {sabado.day} de {m[sabado.month - 1]} de {sabado.year}"


def leer_tema():
    ruta = ROOT / "tema.txt"
    if not ruta.exists():
        return "", []
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    cabecera = [l for l in lineas if l.strip().startswith("#")]
    tema = " ".join(l.strip() for l in lineas if l.strip() and not l.strip().startswith("#"))
    return tema, cabecera


# ---------------------------------------------------------------- Principal
def main():
    hoy = datetime.datetime.now(TZ).date()
    lunes = hoy - datetime.timedelta(days=hoy.weekday())
    semana = hoy.isocalendar()[1]
    historial = json.loads((DATA / "historial.json").read_text(encoding="utf-8"))
    previa = next((h for h in historial if h["fecha"] == hoy.isoformat()), None)
    numero = previa["numero"] if previa else len(historial) + 1
    tema, cabecera_tema = leer_tema()
    modo = (os.environ.get("MODO") or "completa").strip()
    tema_manual = (os.environ.get("TEMA_MANUAL") or "").strip()
    instrucciones = (os.environ.get("INSTRUCCIONES") or "").strip()
    usa_tema_txt = bool(tema) and not tema_manual
    tema = tema_manual or tema
    sistema = (ROOT / "editorial" / "lineas_editoriales.md").read_text(encoding="utf-8").replace("{SITE_URL}", SITE_URL)

    recientes = "; ".join(h["titulo_es"] for h in historial[-8:] if h["fecha"] != hoy.isoformat()) or "ninguno todavía"
    instruccion_tema = (f"Tema del dossier IMPUESTO por el editor: «{tema}». Desarróllalo aunque no sea la noticia principal."
                        if tema else "Elige tú el tema del dossier según la actualidad de la semana.")

    extra = f"Instrucciones adicionales del editor (prioritarias): {instrucciones}\n" if instrucciones else ""
    log(f"Edición N.º {numero}, semana {semana} ({lunes} → {hoy}), modelo {MODELO}, modo {modo}")
    previa_ruta = DATA / "previa.json"
    if modo == "solo_dossier":
        if not previa_ruta.exists():
            raise RuntimeError("Modo «solo_dossier»: no se ha encontrado ninguna edición pendiente de aprobar.")
        previa = json.loads(previa_ruta.read_text(encoding="utf-8"))
        previa_ruta.unlink()
        base_fr = {k: v for k, v in previa["fr"].items() if k != "minutos"}
        user_dossier = (
            f"Fecha de hoy: {hoy.isoformat()}. Semana {semana}: del lunes {lunes.isoformat()} al {hoy.isoformat()}.\n"
            "Esta es la edición francesa ya preparada (JSON). El editor quiere CAMBIAR SOLO EL DOSSIER.\n"
            f"{instruccion_tema}\n{extra}"
            "Investiga el tema con la búsqueda web y redacta un dossier nuevo siguiendo la estructura y la extensión indicadas. "
            "Ajusta también el editorial (para que sea coherente con el nuevo dossier, sin perder lo esencial de la semana) "
            "y los textos de LinkedIn. Devuelve únicamente un JSON con tres claves: «editorial», «dossier» y «linkedin», "
            "con el mismo esquema, entre <json> y </json>. No escribas comentarios entre búsquedas.\n\n"
            + json.dumps(base_fr, ensure_ascii=False)
        )
        nuevo = obtener_edicion(sistema, user_dossier, True)
        for k in ("editorial", "dossier", "linkedin"):
            if nuevo.get(k):
                base_fr[k] = nuevo[k]
        ed_fr = validar(base_fr, "fr")
    else:
        ed_fr = None
    user_fr = (
        f"Fecha de hoy: {hoy.isoformat()}. Semana {semana}: del lunes {lunes.isoformat()} al {hoy.isoformat()}.\n"
        f"Prepara la edición N.º {numero} del boletín en FRANCÉS (edición francesa, público francés).\n"
        f"{instruccion_tema}\n{extra}"
        f"Temas de dossiers recientes, que no debes repetir salvo novedad importante: {recientes}.\n"
        "Investiga primero con la búsqueda web y después devuelve únicamente el JSON entre <json> y </json>.\n"
        "Durante la investigación NO escribas comentarios, planes ni resúmenes intermedios entre búsquedas: "
        "reserva toda la redacción para el JSON final."
    )
    if ed_fr is None:
        ed_fr = validar(obtener_edicion(sistema, user_fr, True), "fr")
    log("Edición francesa lista.")

    user_es = (
        "Aquí tienes la edición francesa de esta semana en JSON. Prepara la edición en ESPAÑOL con exactamente el mismo esquema.\n"
        "Reglas: traduce con fidelidad hechos, cifras, gráficos y fuentes (mismas URLs), con buena prosa española, no una traducción literal. "
        "Adapta los campos «lectura», «puntos_clave», «lectura» del dossier y los textos de LinkedIn al lector español "
        "(empresa o inversor español que mira hacia Francia). No añadas hechos nuevos. "
        "Adapta también las aposiciones explicativas y el «glosario» al lector español: explica con más detalle las siglas e instituciones francesas "
        "y basta una mención breve para las españolas más conocidas. "
        "Usa el formato numérico español (punto para miles, coma para decimales).\n"
        + (f"Ten en cuenta estas instrucciones del editor: {instrucciones}\n" if instrucciones else "") +
        "Devuelve únicamente el JSON entre <json> y </json>.\n\n"
        + json.dumps({k: v for k, v in ed_fr.items() if k != "minutos"}, ensure_ascii=False)
    )
    ed_es = validar(obtener_edicion(sistema, user_es, False), "es")
    log("Edición española lista.")

    fecha = hoy.isoformat()
    ruta_ed = f"/ediciones/{fecha}/"
    meta = {"numero": numero, "semana": semana, "fecha": fecha, "ruta": ruta_ed,
            "rango_fr": rango(lunes, hoy, "fr"), "rango_es": rango(lunes, hoy, "es")}
    historial = [h for h in historial if h["fecha"] != fecha]
    historial.append({"numero": numero, "fecha": fecha, "semana": semana, "ruta": ruta_ed,
                      "titulo_fr": ed_fr["dossier"]["titulo"], "titulo_es": ed_es["dossier"]["titulo"]})
    anteriores = list(reversed(historial[:-1]))

    env = Environment(loader=FileSystemLoader(ROOT / "plantillas"), autoescape=select_autoescape(["html", "j2"]))
    plantilla = env.get_template("boletin.html.j2")
    css = (ROOT / "plantillas" / "estilos.css").read_text(encoding="utf-8")
    html = plantilla.render(fr=ed_fr, es=ed_es, L=LABELS, meta=meta, css=css,
                            archivo=anteriores, linkedin_url=CONFIG.get("linkedin_url", ""), site_url=SITE_URL)
    html_archivo = env.get_template("archivo.html.j2").render(
        L=LABELS, css=css, ediciones=list(reversed(historial)), site_url=SITE_URL)

    (SITE / "ediciones" / fecha).mkdir(parents=True, exist_ok=True)
    (SITE / "ediciones" / fecha / "index.html").write_text(html, encoding="utf-8")
    (SITE / "index.html").write_text(html, encoding="utf-8")
    (SITE / "archivo").mkdir(parents=True, exist_ok=True)
    (SITE / "archivo" / "index.html").write_text(html_archivo, encoding="utf-8")
    (SITE / "CNAME").write_text(SITE_URL.split("//", 1)[1] + "\n", encoding="utf-8")
    (DATA / "historial.json").write_text(json.dumps(historial, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / f"edicion-{fecha}.json").write_text(json.dumps({"fr": ed_fr, "es": ed_es}, ensure_ascii=False, indent=2), encoding="utf-8")
    if usa_tema_txt:
        (ROOT / "tema.txt").write_text("\n".join(cabecera_tema) + "\n", encoding="utf-8")

    OUT.mkdir(exist_ok=True)
    (OUT / f"boletin-rilamax-{fecha}.html").write_text(html, encoding="utf-8")
    for idioma, ed in (("fr", ed_fr), ("es", ed_es)):
        li = ed["linkedin"]
        (OUT / f"linkedin_{idioma}.txt").write_text(
            "=== NEWSLETTER ===\n\n" + li.get("newsletter", "") + "\n\n=== POST ===\n\n" + li.get("post", "") + "\n",
            encoding="utf-8")
    resumen = {"numero": numero, "fecha": fecha, "semana": semana, "modelo": MODELO,
               "dossier_fr": ed_fr["dossier"]["titulo"], "dossier_es": ed_es["dossier"]["titulo"],
               "tema_impuesto": tema, "modo": modo, "instrucciones": instrucciones, "uso": USO, "url_edicion": SITE_URL + ruta_ed}
    (OUT / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "pr_body.md").write_text(
        f"## Bulletin Rilamax N.º {numero} — semana {semana}\n\n"
        f"**Dossier:** {ed_es['dossier']['titulo']}\n\n"
        "Revisa el boletín adjunto en el correo. Si todo está bien, pulsa **Merge pull request** y luego **Confirm merge**: "
        f"la edición se publicará en {SITE_URL} en 2 o 3 minutos.\n\n"
        "Si no quieres publicarla, pulsa **Close pull request**.\n",
        encoding="utf-8")

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"fecha={fecha}\nnumero={numero}\nsemana={semana}\n")
    log(f"Terminado. Uso: {USO}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        OUT.mkdir(exist_ok=True)
        (OUT / "error.txt").write_text(f"{type(e).__name__}: {e}", encoding="utf-8")
        log(f"ERROR: {e}")
        sys.exit(1)
