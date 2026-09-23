# Aire Rápido · v1.6.0

Consulta rápida de las cabinas de calidad del aire del Campo de Gibraltar: lista y mapa con el valor de cada estación, a cualquier hora de cualquier día desde el 25/10/2021, con la tabla numérica hora a hora, gráfica con el valor en cada punto y evolución de 7, 30 o 90 días.

## Cómo funciona

La Junta de Andalucía publica un CSV por provincia y día con los valores horarios de cada estación:
`https://www.juntadeandalucia.es/medioambiente/atmosfera/informes_siva/cuantitativo/AAAA/CA_AAAAMMDD.csv`

El navegador no puede leer esos ficheros directamente (el servidor de la Junta no permite peticiones desde otras webs), así que una GitHub Action los descarga cada hora, se queda con las estaciones del Campo de Gibraltar y los guarda como JSON pequeños dentro del propio repositorio. La web solo lee esos JSON: es estática, gratuita y rápida, y el histórico queda archivado en tu repo aunque la fuente cambie.

```
index.html                       la web completa en un solo archivo (GitHub Pages)
stations.json                    opcional: corrige nombres y coordenadas sin tocar el código
scripts/fetch_junta.py           descarga y procesa los CSV
.github/workflows/actualizar-datos.yml   ejecución horaria y carga histórica
data/AAAA/AAAA-MM-DD.json        un fichero por día (≈10 kB)
data/latest.json                 último día y hora disponibles
data/estaciones_detectadas.json  nombres reales que llegan en el CSV
```

## Publicarla en GitHub

1. Crea un repositorio nuevo (por ejemplo `aire-rapido`) y sube todo el contenido de esta carpeta, incluida `.github`.
2. En **Settings > Actions > General > Workflow permissions**, marca **Read and write permissions** y guarda.
3. En **Settings > Pages**, elige **Deploy from a branch**, rama `main`, carpeta `/ (root)`.
4. En la pestaña **Actions**, abre **Actualizar datos calidad del aire** y pulsa **Run workflow** sin rellenar nada. Al terminar tendrás hoy y ayer en `data/`.
5. Revisa `data/estaciones_detectadas.json`. Si algún nombre no coincide con las claves de `stations.json`, cambia la clave para que sea idéntica (en mayúsculas y sin tildes). Las estaciones sin coordenadas salen en la lista pero no en el mapa.
6. Carga histórica: vuelve a **Run workflow** con `desde` (y opcionalmente `hasta`). Hazlo por años (por ejemplo `2025-01-01` a `2025-12-31`), cada año tarda unos minutos.
7. La web quedará en `https://calidaddelaire.pelayoingenieriadigital.es` (ver “Dominio propio”). En el móvil, “Añadir a pantalla de inicio”.

## Dominio propio: calidaddelaire.pelayoingenieriadigital.es

1. El fichero `CNAME` de la raíz del repositorio ya contiene `calidaddelaire.pelayoingenieriadigital.es`. No lo borres: GitHub Pages lo usa para saber qué dominio servir.
2. En el panel DNS del dominio (IONOS) crea este registro:

   | Tipo  | Host / nombre     | Apunta a                 | TTL      |
   |-------|-------------------|--------------------------|----------|
   | CNAME | `calidaddelaire`  | `sergiopelayo.github.io` | 1 hora   |

   Si ya existe un registro A, AAAA o CNAME con el nombre `calidaddelaire`, elimínalo antes. No toques los registros del dominio principal ni los de la VPS.
3. En GitHub, **Settings > Pages > Custom domain**, comprueba que aparece `calidaddelaire.pelayoingenieriadigital.es` y pulsa **Save**. Espera a que el chequeo DNS salga en verde.
4. Cuando GitHub haya emitido el certificado (de minutos a una hora), marca **Enforce HTTPS**.
5. Opcional pero recomendable: en **Settings > Pages** de tu cuenta (no del repo) verifica el dominio `pelayoingenieriadigital.es` con el registro TXT que te indique GitHub. Así nadie más puede usar subdominios tuyos en GitHub Pages.

Comprobación rápida desde un terminal: `nslookup calidaddelaire.pelayoingenieriadigital.es` debe devolver `sergiopelayo.github.io`.

## Cosas a verificar tras la primera ejecución

- **Formato del CSV.** El script detecta separador, codificación y columnas por el nombre de la cabecera. Si el log de la Action muestra “Sin cabecera reconocible”, pásame las primeras líneas de un CSV real y ajusto el mapeo.
- **Modo demostración.** Mientras no exista `data/latest.json` la web muestra datos simulados con un aviso amarillo. En cuanto la Action genere datos reales, el aviso desaparece solo. Puedes forzarlo con `?demo` al final de la URL.
- **Coordenadas.** Las de `stations.json` son aproximadas (`"aprox": true`). Corrígelas con `Listado_estaciones.xlsx` del conjunto “Datos cuantitativos históricos horarios y diarios de Calidad del Aire en Andalucía” del portal de datos abiertos de la Junta y pon `"aprox": false`.
- **Bloqueo de GitHub.** Si la Junta rechazara las descargas desde los servidores de GitHub, el plan B es ejecutar el mismo script en tu VPS con un cron y hacer `git push`.

## Limitaciones

- Datos horarios **sin validar** por la red; pueden diferir de los informes oficiales, y la Junta puede completar huecos con datos modelizados de CAMS.
- El color del índice sigue los umbrales del Índice Nacional de Calidad del Aire, aplicados al valor horario. Para PM10 y PM2.5 el índice oficial usa medias de 24 h, así que ahí es orientativo.
- Las horas son las del fichero de la Junta (01:00 a 24:00).
- GitHub puede retrasar unos minutos las ejecuciones programadas.

## Polvo africano

El script pide cada hora a Open-Meteo el polvo mineral en superficie que estima el modelo CAMS (Copernicus) en la Bahía de Algeciras y lo guarda en el JSON de cada día (`polvo`, µg/m³, y `aod`, espesor óptico). La carga histórica también lo trae. Es un modelo, no una medida, y los cortes de nivel de la app son orientativos. Para confirmar un episodio con validez oficial usa los episodios naturales que publica el Ministerio (enlace en la hoja “i” de la app).

La API gratuita de Open-Meteo es para uso no comercial. Si la app pasara a ser un producto de Pelayo Ingeniería Digital habría que contratar su plan comercial o descargar CAMS directamente de Copernicus.

## Informes oficiales de intrusiones

Cada hora el script lee la página del Ministerio con las predicciones del mes en curso y del anterior (en la carga histórica, todos los meses del rango) y guarda en `data/miteco_intrusiones.json` qué días tienen informe y el enlace a su PDF. El Ministerio solo publica informe los días en que se prevé intrusión, así que su existencia ya es una señal. El informe cubre toda España: para citarlo hay que comprobar que menciona el sur o el suroeste peninsular, y para descontar superaciones vale el informe anual de episodios naturales validados.

Desde agosto de 2023 el Ministerio tiene una página por mes y el índice es fiable. Antes de esa fecha la página es anual y el índice automático puede quedar incompleto; la app enlaza igualmente al listado de ese año.

## Atribución

Datos: Red de Vigilancia y Control de la Calidad del Aire de Andalucía, Consejería de Sostenibilidad y Medio Ambiente, Junta de Andalucía. Licencia CC BY 4.0. Informes de intrusiones: Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO) y CSIC. Polvo: CAMS (Copernicus Atmosphere Monitoring Service) vía Open-Meteo, CC BY 4.0. Mapa: ortofoto PNOA © Instituto Geográfico Nacional (CC BY 4.0), imagen de satélite © Esri, Maxar, Earthstar Geographics, callejero © colaboradores de OpenStreetMap; costa del esquema de respaldo: Natural Earth (dominio público).

## Versiones

- **1.6.0** (23/09/2026): mapa nuevo con Leaflet. Capas: ortofoto PNOA del IGN con nombres (por defecto), satélite mundial de Esri (cubre también Gibraltar) y callejero de OpenStreetMap; se recuerda la elegida. Pines con el valor y el color del nivel, nombre de la cabina al acercar, ficha rápida al tocar (valores de todos los contaminantes, Ver ficha y Cómo llegar) y tu posición. Si no cargan las imágenes (sin conexión, bloqueo) vuelve solo al esquema de la bahía.
- **1.5.0** (23/09/2026): líneas de valor límite en las gráficas de partículas (PM10: límite diario legal 50 y límite 2030/OMS 45; PM2.5: límite diario 2030 de 25 y OMS 15). Contador de superaciones por cabina y año: días de PM10 por encima de 50 frente a los 35 permitidos, días por encima de 45 frente a los 18 de 2030, cuántos tienen informe de intrusión africana, barras por mes, lista de días y copia para Excel. La media diaria de partículas se toma del valor de las 24:00 (media de 24 h en los ficheros de la Junta). Descarga desde la VPS (`vps/actualizar.sh`, cron cada hora) porque la Junta no responde a los servidores de GitHub; script v1.4.2 con lectura de las cabeceras reales (`D_PROVINCIA`, `'PM10'`…).
- **1.4.1** (23/09/2026): fichero `CNAME` para `calidaddelaire.pelayoingenieriadigital.es` y guía de configuración DNS. Sin cambios en la app ni en el script.
- **1.4.0** (23/09/2026): enlaces a los informes oficiales del Ministerio sobre intrusiones de aire africano. Aviso con el PDF del día en la lista y en la ficha, icono 📄 en las tablas de evolución, listado de informes del periodo en Comparar (y columna en la copia para Excel), y en la hoja “i” los enlaces a las predicciones del mes, a los informes anuales validados, al informe de episodios naturales 2024 y a la metodología oficial. El script (v1.4.0) mantiene `data/miteco_intrusiones.json`. La app trae de serie los informes reales de agosto y septiembre de 2026.
- **1.3.0** (23/09/2026): pestaña Comparar (2 a 6 cabinas superpuestas por horas con etiqueta en cada dato, coeficiente de similitud r entre cabinas y frente al polvo, tabla por horas y copiar para Excel). Polvo africano estimado (modelo CAMS vía Open-Meteo) guardado cada hora junto a los datos: aviso en la lista, franjas color arena en las gráficas, barras de polvo bajo la evolución y enlace a las predicciones oficiales del Ministerio. Script de descarga v1.3.0.
- **1.2.0** (23/09/2026): evolución por horas con gráfica continua desplazable y etiqueta en cada dato (24 h, 48 h, 3 días, 7 días) y tabla de valores por día y hora. Se mantienen las medias diarias de 30 y 90 días. La ficha abre por defecto con PM10 y 48 h, y recuerda el último contaminante y periodo elegidos.
- **1.1.0** (23/09/2026): interfaz nueva tipo app. Tarjeta destacada con la estación más cercana o la peor, días en fichas, barra inferior Lista/Mapa/Cerca de mí, mapa propio de la bahía (sin servicios externos, con zoom y arrastre), botón Cómo llegar a Google Maps, hoja de colores del índice, modo oscuro y modo demostración automático mientras no haya datos reales.
- **1.0.0** (23/09/2026): primera versión. Lista y mapa por hora, selector de fecha, detalle con tabla horaria, gráfica etiquetada, evolución 7/30/90 días, exportar CSV y copiar tabla.
