# Modos del altavoz y animaciones de la comunidad

Guia del fork (26-11) para la sesion de cata de Chele: que sabe hacer el Timebox EVO por si solo,
como se configura desde nuestro panel, y que hay de ver las animaciones que crea la gente.

## 1. Modos nativos del firmware (viven en el altavoz)

El daemon controla el EVO por Bluetooth (perfil serie SPP, canal 1). Estos modos los pinta el
PROPIO firmware y siguen ahi aunque el PC se apague — el ultimo modo enviado manda:

| Modo | Que es | Opciones | Donde se configura |
|---|---|---|---|
| **Reloj** | 6 estilos (pantalla completa, arcoiris, con caja, analogico cuadrado, negativo, analogico redondo) | color; mostrar hora / tiempo / temperatura / calendario | Panel > Modos del altavoz > Reloj |
| **Luz** | lampara de mesa | 5 tipos (color fijo, love, plants, no mosquito, sleeping), color, brillo | Panel > Modos del altavoz > Luz |
| **Efectos** | 16 animaciones de fondo (sparkles, lava, rainbow lines, drops, swirl, CMY fade, fire, countdown, ...) | solo elegir numero | Panel > Modos del altavoz > Efectos |
| **Visualizador** | 11 estilos que reaccionan al sonido del micro interno del altavoz | solo elegir numero (el protocolo no los nombra) | Panel > Modos del altavoz > Visualizador |
| **Marcador** | marcador rojo/azul 0-999 | + / - por equipo, reset | Panel > Modos del altavoz > Marcador |
| **Tiempo** | icono de clima + temperatura que el firmware muestra junto al reloj | clear/cloudy/thunderstorm/rain/snow/fog, grados | Panel > Modos del altavoz > Tiempo y hora (o automaticos: el informe 08:30 de ZERO pinta el icono de Caceres) |
| **Nube** | canal DIY del firmware | — | (no lo usamos) |

Extras que no son modos del firmware sino del daemon (necesitan el PC vivo): temporizador y
cronometro con barra, medidor CPU/RAM, latencia de red, bateria/disco, rejilla de sitios,
rotacion, recordatorios, atenuacion nocturna, **luz nocturna del fork** (tarjeta propia en Ajustes).

Regla de nuestro entorno (24-11): el canal serie comparte radio con el audio A2DP — mientras el
agente esta hablando (flag `memory/evo-talking.txt` < 10 min) NADA debe repintar la pantalla.
Los modos nativos son gratis una vez enviados: el firmware los loopia sin trafico Bluetooth.

## 2. Animaciones creadas por usuarios (galeria Divoom)

- La galeria comunitaria vive en la **app oficial de Divoom** (movil: "Divoom: Pixel art
  community" / web divoom.com). Miles de disenos 16x16 subidos por usuarios; se exploran y se
  envian al altavoz DESDE la app del movil.
- **Limitacion dura**: el altavoz acepta UN controlador Bluetooth. Para ver una animacion de la
  comunidad desde la app hay que liberar el enlace (nuestro daemon deja el altavoz si se para:
  Panel > Ajustes > Detener servicio, o `python divo.py stop`). Al volver, daemon > `start`.
- No existe API publica estable para descargar la galeria; hay proyectos comunitarios
  (p. ej. "servoom") que trastean con la nube de Divoom — NO los hemos validado y no meteremos
  nada de eso en el daemon sin probarlo antes.
- Lo que SI podemos hacer hoy, sin la app y sin tocar la nube: **traer arte externo al altavoz**
  con nuestro pipeline (zero-dependencias por design):
  1. PNG/GIF/BMP (o el link de la imagen que sea) → 16x16 con paleta reducida usando
     `ffmpeg`/Pillow que ya estan en ZERO (fuera del repositorio, solo como ayuda de sesion),
  2. cada frame → 256 tuplas RGB, `---`-estilo del formato de `tools/divo-draw.py`,
  3. envio por la API local fuente `gui` (`frames` 1-12, delay 60-2000 ms) → **el firmware
     loopia la animacion solo** (comando 0x49) — igual que hace con las de la app.
- Es decir: la experiencia "ver animaciones de otros" es mejor desde la app del movil (buscador,
  favoritos, pantalla tactil); la nuestra es buena para FIJAR una eleccion concreta en el EVO
  como cara del agente sin depender del movil.

## 3. Plan de cata sugerido (pendiente de Chele)

1. Abrir el panel (acceso directo ZERO EVO Panel) → pestaña **Modos del altavoz** → recorrer:
   reloj (probar los 6 estilos + calendario), luz, los 16 efectos, los 11 visualizadores
   (poner musica y mirar), marcador.
2. Dec cuales merece tarjeta rapida o rotacion automatica (p. ej. reloj de cuarto ya esta;
   efectos de celebracion podrian ligarse a tareas largas).
3. Decidir si se prueba el flujo comunidad: parar daemon → app del movil de Chele → elegir un
   diseno → verlo en el EVO → relanzar daemon. (Ojo regla 24-11: no hacerlo durante una locucion.)
4. Si se quiere una animacion de la comunidad como fija del agente: capturar/exportar el arte
   (o un GIF equivalente de la web de Divoom) y pasarla por el pipeline del apartado 2.

Nada de esto esta todavia en el daemon (decision de fork: sin uploader ni galeria propia —
ver Limits del README). Si la cata convence, la candidate feature seria un "playground" que
liste los `tools/art/*.txt` propios y los ponga en rotacion — pequeno, sin red, testeable.
