#!/usr/bin/env python3
"""Envía el correo del sábado (revisión) o un aviso de error, vía SMTP de Brevo."""
import html
import json
import os
import pathlib
import smtplib
import sys
from email.message import EmailMessage
from email.utils import formataddr

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def enviar(asunto, cuerpo_html, cuerpo_txt, adjuntos=()):
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = formataddr((CONFIG["nombre_remitente"], CONFIG["correo_remitente"]))
    msg["To"] = CONFIG["correo_destino"]
    msg.set_content(cuerpo_txt)
    msg.add_alternative(cuerpo_html, subtype="html")
    for ruta in adjuntos:
        ruta = pathlib.Path(ruta)
        if ruta.exists():
            sub = "html" if ruta.suffix == ".html" else "plain"
            msg.add_attachment(ruta.read_bytes(), maintype="text", subtype=sub, filename=ruta.name)
    with smtplib.SMTP("smtp-relay.brevo.com", 587, timeout=60) as s:
        s.starttls()
        s.login(os.environ["BREVO_SMTP_LOGIN"], os.environ["BREVO_SMTP_KEY"])
        s.send_message(msg)


def bloque(titulo, texto):
    return (f'<h3 style="margin:28px 0 8px;font-size:16px">{html.escape(titulo)}</h3>'
            f'<div style="white-space:pre-wrap;background:#F5F7FA;border:1px solid #D9DEE7;border-radius:8px;'
            f'padding:14px;font-size:14px;line-height:1.5">{html.escape(texto)}</div>')


def revision():
    r = json.loads((OUT / "resumen.json").read_text(encoding="utf-8"))
    pr = os.environ.get("PR_URL", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    rehacer = f"https://github.com/{repo}/actions/workflows/boletin-semanal.yml"
    li = {i: (OUT / f"linkedin_{i}.txt").read_text(encoding="utf-8") for i in ("fr", "es")}
    uso = r["uso"]
    asunto = f"Bulletin Rilamax N.º {r['numero']} listo para revisar — {r['dossier_es']}"
    cuerpo = f"""<div style="font-family:Arial,sans-serif;color:#16233D;max-width:680px">
<h2 style="margin:0 0 6px">Bulletin Rilamax N.º {r['numero']} — semana {r['semana']}</h2>
<p style="margin:0 0 18px;color:#5A6478">Dossier: <b>{html.escape(r['dossier_es'])}</b> / {html.escape(r['dossier_fr'])}</p>
{('<p style="margin:0 0 18px;font-size:13px;color:#5A6478">Versión rehecha · modo: ' + html.escape(r.get('modo','')) + (' · instrucciones: ' + html.escape(r['instrucciones']) if r.get('instrucciones') else '') + '</p>') if r.get('modo') == 'solo_dossier' or r.get('instrucciones') else ''}
<ol style="line-height:1.6;padding-left:20px">
<li><b>Revisa el boletín</b>: abre el archivo adjunto <i>boletin-rilamax-{r['fecha']}.html</i> en tu navegador (botón FR/ES arriba a la derecha).</li>
<li><b>Si está bien</b>, pulsa el botón de abajo y luego <b>Merge pull request</b> → <b>Confirm merge</b>. Se publicará en {html.escape(r['url_edicion'])} en 2-3 minutos.</li>
<li><b>Publica en LinkedIn</b> con los textos de abajo (también van adjuntos).</li>
</ol>
<p style="margin:22px 0"><a href="{html.escape(pr)}" style="background:#16233D;color:#fff;text-decoration:none;padding:12px 20px;border-radius:8px;font-weight:bold">Revisar y aprobar en GitHub</a></p>
<p style="font-size:13px;color:#5A6478">Si no quieres publicar esta edición, abre el mismo enlace y pulsa <b>Close pull request</b>: no se publicará nada.</p>
<div style="margin:26px 0;padding:16px;border:1px solid #D9DEE7;border-radius:8px;background:#E4F0EE">
<h3 style="margin:0 0 8px;font-size:16px">¿Quieres cambiar algo antes de publicar?</h3>
<ol style="margin:0;padding-left:20px;line-height:1.6;font-size:14px">
<li>Abre <a href="{html.escape(rehacer)}">la página del proceso «Boletín semanal»</a> y pulsa <b>Run workflow</b>.</li>
<li><b>Modo</b>: «solo_dossier» para cambiar solo el dossier (se conservan noticias y cifras) o «completa» para rehacerlo todo.</li>
<li><b>Tema</b>: el tema del dossier que quieres. <b>Instrucciones</b>: cualquier indicación libre.</li>
<li>Pulsa el botón verde <b>Run workflow</b>. En unos minutos recibirás la nueva versión; la anterior se descarta sola.</li>
</ol></div>
{bloque('LinkedIn — Français', li['fr'])}
{bloque('LinkedIn — Español', li['es'])}
<p style="margin-top:28px;font-size:12px;color:#5A6478">Modelo: {html.escape(r['modelo'])} · Búsquedas web: {uso['busquedas']} · Tokens: {uso['input']:,} de entrada, {uso['output']:,} de salida.</p>
</div>"""
    txt = (f"Bulletin Rilamax N.º {r['numero']} listo para revisar.\nAprobar: {pr}\n\n"
           f"LinkedIn FR:\n{li['fr']}\n\nLinkedIn ES:\n{li['es']}\n")
    adj = [OUT / f"boletin-rilamax-{r['fecha']}.html", OUT / "linkedin_fr.txt", OUT / "linkedin_es.txt"]
    enviar(asunto, cuerpo, txt, adj)


def error():
    detalle = (OUT / "error.txt").read_text(encoding="utf-8") if (OUT / "error.txt").exists() else "Ver el registro de la ejecución."
    run = os.environ.get("RUN_URL", "")
    asunto = "Bulletin Rilamax: la edición de esta semana no se ha podido generar"
    cuerpo = f"""<div style="font-family:Arial,sans-serif;color:#16233D;max-width:680px">
<h2>La generación del boletín ha fallado</h2>
<p>No se ha publicado nada. Detalle técnico:</p>
<pre style="white-space:pre-wrap;background:#F5F7FA;padding:12px;border-radius:8px">{html.escape(detalle)}</pre>
<p><a href="{html.escape(run)}">Ver la ejecución en GitHub</a></p>
<p>Puedes relanzarla desde GitHub → Actions → «Boletín semanal» → Run workflow, o copiar este mensaje a Claude para que te ayude.</p>
</div>"""
    enviar(asunto, cuerpo, f"La generación del boletín ha fallado.\n{detalle}\n{run}")


if __name__ == "__main__":
    error() if "--error" in sys.argv else revision()
