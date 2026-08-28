# Clariot — informes de alarmas de vibración a partir del correo

Las alertas de vibración de **Clariot / Alfa Laval** llegan por correo, en inglés y
con un PDF adjunto. Alguien tiene que leerlas, traducirlas, agrupar las que son del
mismo equipo, decidir cuáles son urgentes y escribirle al cliente. Eso toma unos
diez minutos por alerta y no escala.

Este programa hace ese trabajo y **deja un borrador en Outlook listo para revisar**.

> **Nunca envía correo.** Solo crea borradores. No es configurable: no existe una
> línea de código que llame a `Send`. Una persona siempre lee y aprueba antes de
> que algo salga.

---

## Índice

1. [Qué hace el programa y qué queda en manos de la persona](#1-qué-hace-el-programa-y-qué-queda-en-manos-de-la-persona)
2. [Requisitos](#2-requisitos)
3. [Instalación paso a paso](#3-instalación-paso-a-paso)
4. [Las carpetas de Outlook y sus nombres](#4-las-carpetas-de-outlook-y-sus-nombres)
5. [La regla de Outlook](#5-la-regla-de-outlook)
6. [La primera prueba](#6-la-primera-prueba)
7. [El uso de todos los días](#7-el-uso-de-todos-los-días)
8. [Comandos](#8-comandos)
9. [La regla de gravedad](#9-la-regla-de-gravedad)
10. [La traducción, en tres capas](#10-la-traducción-en-tres-capas)
11. [Cómo evita duplicados](#11-cómo-evita-duplicados)
12. [Configuración](#12-configuración)
13. [Estructura del código](#13-estructura-del-código)
14. [Tests](#14-tests)
15. [Límites conocidos](#15-límites-conocidos)

---

## 1. Qué hace el programa y qué queda en manos de la persona

| Paso | Quién |
| --- | --- |
| Detectar la alerta nueva en la carpeta | programa |
| Leer el PDF y extraer los datos | programa |
| Agrupar con las alarmas anteriores del mismo equipo | programa |
| Clasificar la gravedad | programa |
| Traducir las frases técnicas al español | programa |
| Redactar el informe y adjuntar los PDF | programa |
| Dejarlo en `Urgencias` o en `Por enviar` | programa |
| **Poner el destinatario y el nombre del contacto** | persona |
| **Escribir la recomendación propia** | persona |
| Leer y enviar | persona |

El destinatario **va vacío a propósito**. El correo de alerta no dice a quién hay
que avisarle: trae la empresa, no el contacto. El técnico lo sabe de memoria y
ponerlo le toma segundos. Y como Outlook se niega a enviar un mensaje sin
destinatario, un borrador a medio terminar **no puede salir por accidente**.

## 2. Requisitos

| | Detalle |
| --- | --- |
| Sistema | Windows 10 u 11 |
| Correo | **Outlook clásico de escritorio**, con la cuenta que recibe las alertas ya configurada |
| Python | 3.10 o superior |
| Clave de IA | Una clave de [Google AI Studio](https://aistudio.google.com/apikey), gratuita y **sin tarjeta** |

**El "nuevo Outlook" no sirve.** No expone COM, que es la interfaz por la que este
programa habla con el correo. Si al abrir Outlook ves un interruptor arriba a la
derecha que dice "Nuevo Outlook", apagalo. Microsoft retira el clásico de las
suscripciones empresariales en 2028 y termina el soporte en abril de 2029; migrar a
Microsoft Graph tocaría **un solo archivo**, `src/clariot/adapters/outlook.py`.

**No hace falta** ninguna App Registration en Azure AD, ningún permiso de
administrador, ni OAuth, ni Microsoft Graph. El programa usa la sesión de Outlook
que ya está abierta en el escritorio. Esa fue una restricción de diseño desde el
principio: en muchas empresas conseguir un registro de aplicación es imposible.

## 3. Instalación paso a paso

Todo se ejecuta en **CMD**, el símbolo del sistema de Windows. Para abrirlo:
`Windows + R`, escribir `cmd`, Enter.

> **CMD y no PowerShell.** No es preferencia: en PowerShell, `activate.bat`
> **falla en silencio**. Un `.bat` corre en un proceso hijo, hace su trabajo y
> muere sin devolverle las variables al PowerShell padre. No da error, no aparece
> `(.venv)`, y los `pip install` siguientes se instalan en el Python del sistema
> sin avisar. Pasó en una instalación real y costó media hora.
>
> Si necesitás PowerShell, el equivalente es `.\.venv\Scripts\Activate.ps1` — otro
> archivo, no el `.bat`.

Para instalarlo en el equipo de un técnico que no tiene nada instalado, seguí
**[DESPLIEGUE.md](DESPLIEGUE.md)**: es este mismo camino, con checklist y con las
pantallas del instalador de Python explicadas una por una.

### Qué hay que tener a mano antes de empezar

Cuatro cosas. Sin la tercera la instalación se traba en el paso 7:

| | Qué | Dónde se consigue |
| --- | --- | --- |
| 1 | **Outlook clásico** instalado y con la cuenta que recibe las alertas | Viene con Microsoft 365. Se verifica con `reg query HKEY_CLASSES_ROOT\Outlook.Application\CLSID` |
| 2 | **Acceso al repositorio** | La cuenta de GitHub con permiso, o el ZIP descargado |
| 3 | **La clave de Gemini** | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — gratis, sin tarjeta. **No viene en el repositorio** |
| 4 | **Un PDF de alerta real** | Para la prueba del final, si todavía no llegó ninguna al buzón |

### Lo único que NO se automatiza

De toda la instalación, **solo dos cosas las tiene que hacer una persona a mano**.
Todo lo demás es un comando.

| | Qué | Por qué no se automatiza |
| --- | --- | --- |
| 1 | **Pegar la clave de Gemini** en `.env` (paso 5) | Es un secreto. No viaja en el repositorio ni puede, y sin ella el programa no arranca |
| 2 | **Crear la regla de Outlook** (paso 8) | Se crea del lado del servidor, desde el navegador, para que funcione con el equipo apagado. El programa no toca las reglas del buzón |

Las **carpetas sí se crean solas** con `--setup-folders`, y las bases de datos y
carpetas de trabajo se generan en la primera corrida. No hay que crear nada a mano
en el disco.

Si al terminar la instalación algo no funciona, empezá por esas dos: en la práctica
son el origen de casi todas las fallas. Sin la clave, `--self-check` se detiene en
el paso 7. Sin la regla, las alertas nunca llegan a la carpeta y el programa corre
sobre una carpeta vacía sin quejarse — porque para él, no tener alertas es normal.

### Paso 1 — Instalar Python

Lo más rápido, desde la consola. Windows 11 ya trae `winget`:

```cmd
winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
```

Instala sin pantallas y deja el PATH puesto. **Se elige 3.12 y no la última**: es la
versión con la que están probadas `pywin32` y `pymupdf`, las dos librerías que hacen
el trabajo pesado.

Si `winget` no está o falla, bajalo de
[python.org](https://www.python.org/downloads/windows/) y en la **primera pantalla**
marcá la casilla **"Add python.exe to PATH"**. Es la más importante: sin ella no
funciona ningún comando de acá. Y **no lo instales desde la Microsoft Store** — esa
versión corre aislada y da problemas justo con `pywin32`.

Cerrá la ventana de CMD, abrí una nueva —los cambios de PATH solo aplican a
ventanas nuevas— y verificá:

```cmd
python --version
```

Tiene que responder `Python 3.12` o similar. Si dice "no se reconoce como un
comando interno o externo", la casilla del PATH no quedó marcada.

### Paso 2 — Bajar el proyecto

```cmd
cd /d C:\
git clone <URL-DEL-REPO> clariot
cd clariot
```

> **No clones dentro de `C:\Users`.** Falla con
> `fatal: could not create work tree dir`: es una carpeta protegida de Windows y no
> se puede escribir sin administrador. `C:\Users` guarda perfiles. La carpeta va en
> `C:\clariot`, o dentro del perfil (`C:\Users\<usuario>\clariot`), que sí es
> escribible.

Siendo un repositorio privado, Git pide autenticación: abre una ventana del
navegador para entrar con la cuenta de GitHub. Si en cambio pide usuario y
contraseña en la consola, la contraseña de GitHub ya no sirve desde 2021 — hay que
generar un token en Settings → Developer settings → Personal access tokens, con
permiso `repo`.

Sin Git instalado: descargá el ZIP del repositorio, descomprimilo y movelo a
`C:\clariot`.

**No lo dejes en el Escritorio ni en Documentos.** Con la copia de seguridad de
OneDrive activada esas carpetas están sincronizadas, y OneDrive sube los archivos
mientras cambian. El programa escribe dos bases SQLite en `state\` durante cada
corrida; subir una base abierta puede bloquearla o corromperla, y perder
`ledger.db` significa perder el registro de qué correos ya se procesaron.

Se reconoce mirando la ruta: si dice `OneDrive`, está sincronizada. El acceso
directo del Escritorio sí puede quedar ahí — es solo un puntero al `.bat`.

### Paso 3 — Crear el entorno virtual

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

El prompt tiene que quedar con `(.venv)` adelante:

```
(.venv) C:\clariot>
```

**Si no lo tiene, no sigas.** Todo lo que viene se instalaría en el Python del
sistema. Hay que activarlo en cada ventana nueva.

### Paso 4 — Instalar las dependencias

```cmd
pip install -r requirements.txt
pip install -e .
```

**Las dos líneas.** La segunda es la que registra el paquete `clariot`; sin ella,
cualquier comando responde `No module named clariot`.

### Paso 5 — La clave de Gemini

Sacá una clave en [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
Es gratuita y no pide tarjeta. Después:

```cmd
copy config\env.example .env
notepad .env
```

Buscá la línea `GEMINI_API_KEY=` y pegá la clave pegada al signo igual, sin espacios
y sin comillas:

```
GEMINI_API_KEY=AIzaSyA...
```

Guardá con `Ctrl + S`. Las demás líneas quedan vacías: son para traducir el PDF
adjunto, que hoy está desactivado. El archivo `.env` está en `.gitignore` y no se
versiona nunca.

### Paso 6 — Crear las carpetas en Outlook

Con Outlook abierto:

```cmd
python -m clariot --setup-folders
```

Crea las cuatro carpetas con los nombres que están en `config/settings.yaml`. Ver
la sección siguiente si querés usar otros nombres.

### Paso 7 — Verificar que todo esté conectado

```cmd
python -m clariot --self-check
```

Una salida sana se ve así:

```
Destinatarios precargados: 0 (0 es lo normal)
Outlook               : conectado
Carpeta 'Clariot': OK (0 correo(s) por revisar)
PDF adjunto           : sin traducir (translation.provider: none)
Frases (gemini)       : modelo gemini-flash-latest, cuota gratuita de AI Studio

Todo listo.
```

Si algo falta, lo dice con nombre y apellido. **No sigas hasta ver `Todo listo`.**

### Paso 8 — La regla de Outlook

Ver la [sección 5](#5-la-regla-de-outlook). Es lo que hace que las alertas caigan
en la carpeta de origen.

### Paso 9 — El acceso directo

Hacé clic derecho sobre `Procesar alertas.bat` → **Enviar a** → **Escritorio (crear
acceso directo)**. Con eso el uso diario es un doble clic, sin consola y sin
comandos que recordar.

## 4. Las carpetas de Outlook y sus nombres

Son cuatro, y **los nombres tienen que coincidir entre Outlook y
`config/settings.yaml`**. No importa cuáles elijas; importa que sean los mismos en
los dos lados.

```
Bandeja de entrada
├── Clariot          <- acá llegan las alertas (la regla las trae)
└── Procesados       <- acá van los originales ya procesados

Borradores
├── Urgencias        <- lo que hay que enviar HOY
└── Por enviar       <- rutina
```

Estos son los valores por defecto en `config/settings.yaml`:

| Carpeta | Clave en `settings.yaml` | Vive bajo |
| --- | --- | --- |
| `Clariot` | `outlook.source_folders` | Bandeja de entrada |
| `Procesados` | `outlook.processed_folder` | Bandeja de entrada |
| `Por enviar` | `outlook.draft_folder` | Borradores |
| `Urgencias` | `outlook.urgent_draft_folder` | Borradores |

**Si querés otros nombres**, editá `config/settings.yaml` primero y después corré
`python -m clariot --setup-folders`: el programa las crea con los nombres nuevos.
Si en cambio las renombrás a mano en Outlook y no tocás el YAML, el programa va a
buscar carpetas que ya no existen y `--self-check` te lo va a decir.

Dos detalles que no son arbitrarios:

- **Los borradores viven bajo `Borradores`, no bajo la Bandeja de entrada.** Un
  mensaje sin enviar solo se abre en modo redacción, con el botón Enviar activo, si
  está bajo Borradores. Eso lo controla `outlook.draft_folder_parent: "drafts"`.
- **Se pueden usar subcarpetas** dentro de la de origen, por ejemplo
  `Clariot/ClienteA`. Con `include_subfolders: true` se leen todas, y el original
  se archiva en la subcarpeta espejo: `Procesados/ClienteA`.

## 5. La regla de Outlook

La regla nativa de Outlook es la que mueve las alertas a la carpeta de origen. Se
crea **una sola vez**, y conviene hacerla desde el navegador
([outlook.office.com](https://outlook.office.com) → engranaje → Correo → Reglas)
para que quede del lado del servidor y funcione con Outlook cerrado.

| Campo | Valor |
| --- | --- |
| Nombre | `Alertas Clariot` |
| Condición | **De** → `support@aliotportal.com` |
| Acción | **Mover a** → `Clariot` |

**Por remitente, no por asunto.** El asunto de las alertas es
`Event notification report - VX-0000000.`, donde la última parte es el número de
serie del equipo y cambia en cada alerta. Peor: el PDF adjunto se llama
`Event Report - 1st Notification`, y ese "1st" sugiere que hay seguimientos con otra
redacción. Una regla por asunto fallaría **en silencio** justo con las alarmas
repetidas, que son las que más importan.

Al guardar, Outlook ofrece dos casillas:

- **"Detener el procesamiento de otras reglas"** — marcala si no tenés otra regla
  que deba ver estos correos.
- **"Ejecutar la regla ahora"** — marcala solo si querés que las alertas que ya
  están en la bandeja se muevan también.

## 6. La primera prueba

No hace falta esperar una alerta real. El programa puede inyectar una de prueba en
la carpeta de origen, sin enviar ni recibir nada:

```cmd
python -m clariot --preview "ruta\al\reporte.pdf"
```

Escribe `preview.html`. Abrilo en el navegador: es exactamente el cuerpo del correo
que se generaría. Si el PDF se leyó mal, se ve acá y no hiciste nada todavía.

```cmd
python -m clariot --dry-run
```

Recorre la carpeta y dice qué haría, **sin escribir nada** en ningún lado: ni
borradores, ni bases de datos, ni archivos.

```cmd
python -m clariot --simulate "ruta\al\reporte.pdf"
python -m clariot
```

La primera línea deja una alerta de prueba en la carpeta de origen; la segunda la
procesa de verdad. Revisá el borrador en Outlook y después borrá el mensaje de
prueba de `Procesados`.

## 7. El uso de todos los días

**Doble clic en el acceso directo**, con Outlook abierto.

El programa no es un servicio que vigila el buzón: arranca, hace su trabajo y se
cierra. Si nadie lo arranca **no se pierde nada** — las alertas se acumulan en la
carpeta de origen y el día que se corra, se procesan todas.

Al terminar, la ventana dice en qué orden revisar:

```
1. Borradores / Urgencias    <- enviar HOY
2. Borradores / Por enviar   <- rutina
```

En cada borrador: poner el destinatario, reemplazar `[NOMBRE]`, completar la
recomendación propia donde dice `[COMPLETAR]`, leer y enviar.

**Se puede automatizar** con el Programador de tareas de Windows, cada 15 minutos,
pero **solo con la opción "ejecutar únicamente cuando el usuario haya iniciado
sesión"**. La otra opción corre sin escritorio interactivo y Outlook no responde;
la tarea falla siempre.

## 8. Comandos

```cmd
python -m clariot                    # operación normal
python -m clariot --self-check       # verifica Outlook, carpetas y clave
python -m clariot --setup-folders    # crea las carpetas de Outlook
python -m clariot --preview PDF      # ver el informe de un PDF, sin tocar nada
python -m clariot --dry-run          # recorre sin escribir nada
python -m clariot --simulate PDF     # inyecta una alerta de prueba
python -m clariot --revisar-frases   # auditar lo que tradujo la IA
python -m clariot --pending          # lo retenido y lo que espera informe semanal
python -m clariot --report           # informe semanal consolidado por cliente
python -m clariot --limit 5          # procesar como máximo 5 correos
python -m clariot --verbose          # log detallado
```

## 9. La regla de gravedad

| Situación | Asunto | Carpeta |
| --- | --- | --- |
| 2+ alarmas del mismo equipo **el mismo día** | `[CRITICO]` | `Urgencias` |
| 2+ alarmas del mismo equipo **en 7 días** | `[URGENTE]` | `Urgencias` |
| Urgencia declarada por el reporte | `[URGENTE]` | `Urgencias` |
| Alarma aislada | sin prefijo | `Por enviar` |

La ventana de 7 días se cuenta **hacia atrás desde la fecha de la alarma**, no
desde el lunes. Un par domingo–lunes, que son ocho horas de diferencia, cuenta como
repetición; con semanas de calendario quedaría partido en dos y no se detectaría.

**Un solo borrador por equipo, que va creciendo.** La segunda alarma no crea otro
correo: actualiza el existente, suma su PDF y lo mueve de carpeta si la gravedad
subió. La gravedad de un borrador es **la peor que alcanzó el equipo**, nunca la de
la alarma que llegó última.

**El cuerpo lleva el detalle de cada condición distinta**, no solo la última. Si la
bomba repite la misma holgura tres veces, sale un bloque con esa condición y sus
tres fechas. Si manda holgura y después un rodamiento, salen dos bloques.

**Un informe sale solo si la gravedad sube.** Sin esa regla, la cuarta alarma del
día generaría otro `[CRITICO]` y la palabra dejaría de significar algo.

**Una vez enviado, lo enviado no vuelve.** Si llega una alarma nueva sobre un equipo
cuyo borrador ya salió, el borrador nuevo detalla solo la nueva, adjunta solo su
PDF, y una línea explica de dónde viene la gravedad: *"Este equipo acumula 4
alarmas desde el 22 de julio. Las 3 anteriores ya fueron informadas."*

**Si el técnico ya editó un borrador, el programa no lo toca** y la alarma nueva va
aparte. Su trabajo nunca se pierde.

## 10. La traducción, en tres capas

```
Frase entra
   ├─ 1. config/glossary.yaml   -> la redacción aprobada. Siempre gana
   ├─ 2. la caché en events.db  -> ya traducida una vez. Gratis e idéntica
   └─ 3. Gemini la traduce      -> SE GUARDA -> desde ahora es la capa 2
```

**La capa 2 es la que hace esto confiable.** Un servicio de traducción preguntado
dos veces puede responder distinto, y un cliente que compara el informe de enero con
el de marzo vería la misma condición descrita de dos formas. Guardar la primera
respuesta lo elimina. Hay un test que simula al servicio cambiando de opinión y
verifica que gana la versión guardada.

Lo que viaja a Gemini es **solo la frase técnica**: sin cliente, planta, equipo ni
número de serie. Hay un test que lo verifica.

`python -m clariot --revisar-frases` lista todo lo que tradujo la IA, para auditarlo
y anular desde `glossary.yaml` lo que no guste.

**El PDF adjunto queda en su idioma original.** Traducirlo está construido pero
desactivado: cuesta unos USD 0,08 por página y necesita facturación de Google
Cloud. Se activa cambiando `translation.provider` a `"google"` en
`config/settings.yaml`.

## 11. Cómo evita duplicados

Dos protecciones, en capas distintas:

- **`state/ledger.db`** — ¿ya procesé este **correo**? Indexado por el `Message-ID`
  de internet, que sobrevive a los movimientos entre carpetas (el `EntryID` de
  Outlook, no). El flag de leído de Outlook **no** es la fuente de verdad: alcanza
  con que alguien abra el correo para mirar el adjunto y esa alerta se volvería
  invisible.
- **`state/events.db`** — ¿ya conté este **evento**? La clave es el equipo más la
  marca de tiempo del reporte. Los sistemas de alerta reenvían notificaciones, y
  contar correos dispararía una urgencia falsa por un solo problema real.

El equipo se identifica por **número de serie**, no por nombre: los nombres se
escriben distinto entre reportes, los números de serie no.

Cada corrida archiva el PDF original en `archive/AAAA-MM/`, con su nombre de
archivo intacto, y agrega una fila a `archive/audit.csv` con la decisión tomada y su
razón. Son tres respaldos: el correo completo en `Procesados`, el PDF en `archive/`,
y la decisión en el CSV.

## 12. Configuración

| Archivo | Para qué |
| --- | --- |
| `config/settings.yaml` | Carpetas, umbrales de gravedad, asuntos, proveedores |
| `config/glossary.yaml` | Frases aprobadas y vocabulario técnico |
| `config/pdf_labels.yaml` | Etiquetas del PDF a buscar (inglés y español) |
| `config/clients.yaml` | Opcional: destinatarios precargados |
| `templates/*.j2` | Cuerpo de los correos |

El color corporativo de los correos es **una sola línea**: `reports.brand_color` en
`config/settings.yaml`. Las dos plantillas derivan de ahí. Todos los bloques del
cuerpo declaran el mismo ancho como atributo HTML, porque el motor de Word que usa
Outlook ignora `max-width` y sin eso cada bloque colapsa al ancho de su contenido.
| `.env` | La clave de Gemini. Nunca se versiona |

Todos los YAML están comentados línea por línea. Los umbrales que más se ajustan
viven en `grouping`: `window_days`, `urgent_threshold`, `urgency_cooldown_days`,
`retention_days`.

## 13. Estructura del código

```
src/clariot/
├── __main__.py          la línea de comandos
│
│  --- núcleo puro, testeable sin Outlook ni red ---
├── models.py            AlertReport, ClientRoute, DraftContent
├── textutils.py         normalización sin acentos, nombres de archivo seguros
├── pdf_parser.py        lee el PDF por coordenadas (ver su docstring: es el
│                        módulo que más costó y explica por qué)
├── glossary.py          las frases aprobadas
├── resolver.py          las tres capas de traducción
├── store.py             eventos, caché de frases, borradores abiertos
├── ledger.py            qué correos ya se procesaron
├── classifier.py        normal / urgente / crítico
├── aggregate.py         agrupa por equipo y por cliente, fechas en castellano
├── report_builder.py    arma los borradores y el entorno de plantillas
├── audit.py             el CSV de trazabilidad
├── ingest.py            el flujo de captura
├── weekly.py            el informe semanal consolidado (opcional)
│
│  --- adaptadores al mundo exterior ---
└── adapters/
    ├── outlook.py            COM. El único archivo que sabe de Outlook
    ├── gemini_text.py        frases, por HTTP sin SDK
    ├── google_text.py        frases, alternativa por Google Cloud
    └── google_translator.py  el PDF, por Google Cloud
```

La regla de la estructura: **todo lo que decide algo es puro y testeable**; todo lo
que habla con el mundo vive en `adapters/`. Por eso los tests corren en cuatro
segundos sin Outlook, sin red y sin claves.

## 14. Tests

```cmd
pytest
```

164 tests en cuatro segundos. Cubren el parseo por coordenadas, el glosario, las
tres capas de traducción, la clasificación de gravedad, la agregación, el armado de
informes y la idempotencia.

Hay dos archivos de test que corren contra **reportes reales de Alfa Laval**. Esos
PDF **no están en el repositorio**: llevan la empresa, planta, equipo y número de
serie de un cliente real, y `Imagenes/` está en `.gitignore` por eso. Los dos tests
se saltan solos cuando el archivo no está, así que `pytest` queda en verde en una
copia recién clonada.

Outlook vive en `adapters/` y se verifica con `--self-check` y `--simulate` contra el
entorno real.

## 15. Límites conocidos

- **El programa nunca envía correo.** Por diseño, y no es configurable.
- **Requiere Outlook clásico abierto**, y una sesión de Windows iniciada. No corre
  como servicio.
- **Un correo con dos PDF no se procesa.** Un reporte real trae uno solo; con dos no
  hay forma honesta de elegir, y tomar el primero descartaría una alarma en
  silencio. El correo queda en la carpeta de origen y la consola lo avisa en cada
  corrida hasta que alguien lo mire.
- **La hora del reporte se copia tal cual, sin convertir.** La etiqueta del PDF es
  `Time Of Event (UTC)` y ese valor pasa al correo sin tocarlo. En Chile, que es
  UTC−4, un correo que dice "24 de julio, 21:05" corresponde a las 17:05 locales, y
  la regla de "dos alarmas el mismo día" compara el día UTC. Decisión explícita: el
  correo dice exactamente lo que dice el reporte del fabricante.
- **Las fechas se leen como día-mes-año**, verificado contra un reporte real. Si
  alguna vez llega uno con formato mes-día, hay que ajustar `_DATE_FORMATS` en
  `src/clariot/store.py`.
- Una bomba que alarma cada 10 días no se agrupa: la ventana es de 7 días,
  configurable en `grouping.window_days`.
- El PDF adjunto queda en su idioma original.
- Los gráficos de vibración no se traducen nunca: son imágenes.
- Máximo 20 adjuntos por borrador, para que un equipo con cincuenta alarmas no
  genere un correo que el servidor rechace.
