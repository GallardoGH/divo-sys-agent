# TODO — divo-sys-agent (aplicacion)

Roadmap del fork como aplicacion propia.rama de trabajo: `DESTROYER`; `main` = estable.

## Identidad y empaquetado
- [x] Ventana nativa del panel: `divo.py gui` abre ventana WebView2 propia (`divosys/panel.py`, 26-11; fallback Edge/Chrome --app). Falta renombrar el exe del launcher a `divo-sys-agent.exe` (punto siguiente).
- [ ] Renombrar por dentro: divo-sys -> divo-sys-agent (exe, entrada de autostart, nombre en Apps de Windows, datos en %LOCALAPPDATA%) sin romper instalaciones existentes (migracion de settings).
- [ ] `divo-sys-agent-setup.exe` publicable con version/checksum del fork (a la vez que se decide si se publica como release).

## Panel
- [x] Identidad del fork en el panel: clave `agent` (migrada desde `claude`), `/api/agent` (alias `/api/claude`), textos es/en "el agente"; Claude solo como forma de payloads de hook (26-11). Pendiente retocar descripciones sueltas de paginas si algo chirria (cata por Chele).
- [ ] Tarjeta "Audio": exposicion de las palancas del pipeline de voz por altavoz (segmentacion en silencios, gaps, filtro, compresor, normalizacion, umbral de verificacion) + boton "test de audio" que mide el enlace y saca verde/rojo.
- [ ] Selector de "agente" (OpenClaw principal, Opencode opcional; Claude Code queda fuera de la integracion por defecto, hooks off).

## Caras
- [ ] Galeria/gestion de caras del fork (17 moods) accesible y editable via ficheros JSON de arte (editor in-app NO: se recomendara pipeline PNG externo -> conversor `--imagen`, media hora de trabajo).
- [ ] Modo "boca al hablar" (animacion talkin en bucle local durante locucion) documentado en la UI.

## Comportamiento (vigilancia, no sobrecarga)
- [ ] El panel debe dejar configurar sin fichas tecnicas: umbrales de fase (idle/bored/sleep, brillo por tramo) ya viven en settings; exponerlos con sliders.
- [ ] "Notificaciones de automatizaciones" (gateway/crons) como tarjeta de estado dentro del panel, leyendo el registro del engine (no anadir trafico nuevo: el watchdog ya existe como script externo).

## Calidad
- [ ] Cada bloque entra por rama, tests (stdlib-only, sin altavoz), merge a main del runtime, reinstall, demo. Lo generalizable se ofrece a upstream como PR (regla del proyecto: nada se publica sin aprobacion humana previa).

## Parked / descartados
- Editor de pixeles in-app (mejor herramientas externas).
- Temporizador de cocina por voz (funcion muy especifica, probable descarte).
- Huevos de pascua por fechas (reserva de comportamiento, futuro).
- Puente ESP32 BLE-WiFi (fase 3, hardware).
