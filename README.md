# Le Bulletin Rilamax / El Boletín Rilamax

Boletín semanal franco-español de economía, finanzas y política, publicado por RILAMAX 2025 SL en https://bulletin.rilamax.com

## Cómo funciona

1. Cada sábado a las 03:00 UTC, el flujo **Boletín semanal** investiga la semana con Claude, redacta la edición en francés y en español, y la deja preparada como *pull request*.
2. Se envía un correo de revisión a admin@rilamax2025.com con el boletín adjunto y los textos de LinkedIn.
3. Al aprobar (Merge pull request → Confirm merge), el flujo **Publicar web** publica la edición en la web.

## Archivos útiles

- `tema.txt`: escribe aquí un tema para el dossier de la próxima edición (opcional).
- `config.json`: modelo de Claude, número máximo de búsquedas, correos y enlace de LinkedIn.
- `editorial/lineas_editoriales.md`: la línea editorial y el formato que sigue Claude.
- `plantillas/`: diseño del boletín.

Las claves están guardadas en Settings → Secrets and variables → Actions (nunca en los archivos).
