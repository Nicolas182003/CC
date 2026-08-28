# Estado del proyecto

> ### ¿Venís a instalarlo? Este no es el documento.
>
> El paso a paso está en **[DESPLIEGUE.md](DESPLIEGUE.md)** — 11 pasos numerados
> desde un equipo sin nada instalado, con las verificaciones de cada uno y una
> tabla de qué hacer si algo falla. La versión corta está en la sección 3 del
> [README](README.md).
>
> **Este archivo es otra cosa:** el registro de qué se decidió, por qué, y qué se
> aprendió rompiendo cosas. Se lee cuando hay que *cambiar* el sistema o entender
> por qué está hecho así, no cuando hay que instalarlo.

Última revisión: 31 de julio de 2026.

El sistema funciona de punta a punta y está probado contra Outlook real: 166 tests
automatizados en verde, más una prueba de carga de 20 alertas. El código vive en un
repositorio privado, y hay **una instalación en producción** en el equipo de un
técnico (el detalle, en la sección 5).

---

## 1. Qué hace hoy

Llega una alerta de Clariot → el programa la lee, la agrupa con las anteriores del
mismo equipo, clasifica la gravedad, y **deja un borrador en Outlook** con el
informe en español y el PDF adjunto. El técnico pone el destinatario, escribe su
recomendación y envía.

| Componente | Estado |
| --- | --- |
| Conexión con Outlook (COM) | **Verificado contra Outlook real** |
| Lectura del PDF por coordenadas | **Verificado con un reporte real de un cliente** |
| Almacén de eventos, sin doble conteo | **Verificado** |
| Clasificación normal / urgente / crítico | **Verificado** |
| Un borrador por equipo que va creciendo | **Verificado** |
| Traducción de frases con IA + caché | **Verificado con Gemini real** |
| Creación y actualización de borradores | **Verificado** |
| Protección contra duplicados | **Verificado** |
| Auditoría en CSV | **Verificado** |
| Traducción del PDF adjunto | Código listo, **bloqueado por facturación** |

---

## 2. Las decisiones y su razón

### El proyecto cambió de objetivo a mitad de camino

Empezó como "traducir el PDF y reenviarlo". Se convirtió en **agrupar alarmas por
equipo y clasificar la gravedad**, porque reenviar no aporta ingeniería: el cliente
podría traducir el PDF solo.

El dato que el flujo original escondía: **cuántas veces alarmó cada equipo.** Una
bomba con cuatro alarmas en la semana es una conversación distinta a cuatro bombas
con una alarma cada una.

### La regla de gravedad

| Patrón | Nivel | Asunto | Carpeta |
| --- | --- | --- | --- |
| 2+ alarmas del mismo equipo **el mismo día** | crítico | `[CRITICO]` | `Urgencias` |
| 2+ alarmas del mismo equipo en 7 días | urgente | `[URGENTE]` | `Urgencias` |
| Urgencia declarada por el reporte | urgente | `[URGENTE]` | `Urgencias` |
| Alarma aislada | normal | sin prefijo | `Por enviar` |

### Un solo borrador por equipo, que crece

```
1ª alarma       -> borrador nuevo en "Por enviar", 1 PDF
2ª esa semana   -> EL MISMO borrador: 2 PDFs, pasa a "Urgencias" como [URGENTE]
3ª el mismo día -> EL MISMO borrador: 3 PDFs, pasa a [CRITICO]
```

El cliente recibe **un correo por equipo**, no uno por alarma.

Y **un informe sale solo si la gravedad sube.** Sin esa regla, la cuarta alarma del
día habría generado otro `[CRITICO]`, y la palabra dejaría de significar algo.

### El cuerpo lleva el detalle de cada condición, no solo la última

Un bloque por **condición distinta**, no uno por alarma y no solo la más reciente.

```
3 alarmas, la misma holgura   -> UN bloque: la condicion + "3 alarmas · 22, 23 y 24 de julio"
2 holguras + 1 rodamiento     -> DOS bloques, el mas reciente primero
```

Agrupado a propósito: una bomba que alarma tres veces por la misma holgura manda
tres reportes con la redacción idéntica, y repetir ese párrafo tres veces se lee
como un error. Lo que el cliente necesita es la condición una vez y las fechas en
que pasó.

Mostrar solo la última alarma —como estaba antes— **borraba del correo la condición
anterior** cuando las fallas eran distintas: el cliente veía "Rodamiento" en la
tabla y nunca se enteraba de qué decía el monitoreo sobre la holgura.

### Una vez enviado, lo enviado no vuelve

Si el borrador ya salió y llega una alarma nueva, el borrador nuevo detalla **solo
la nueva**, adjunta **solo su PDF**, y una línea de contexto explica de dónde sale
la gravedad: *"Este equipo acumula 4 alarmas desde el 22 de julio. Las 3 anteriores
ya fueron informadas; a continuación el detalle de la nueva."*

Reenviar lo que el cliente ya leyó se lee como un error, y el conteo total sigue
siendo la señal de gravedad. Cada evento guarda el informe en que salió, así que la
auditoría dice la verdad.

### Un correo con dos PDFs no se procesa

Un reporte real trae **un** PDF. Si llegan dos, no hay forma honesta de elegir:
tomar el primero descartaría una alarma en silencio, y contar alarmas es la razón
de existir del sistema.

Así que no se procesa. El correo **queda en la carpeta de origen** y la consola lo
grita en cada corrida —`ATENCION: 1 correo(s) con mas de un PDF, SIN PROCESAR`—
hasta que alguien lo mire. Archivarlo lo haría desaparecer en silencio, que es
justo la falla que esta rama existe para evitar.

### La hora del reporte se copia tal cual, sin convertir

La etiqueta del PDF es `Time Of Event (UTC)` y ese valor pasa al correo sin
tocarlo. **Decisión explícita del equipo:** no deducir ni convertir nada.

Consecuencia conocida: en julio Chile es UTC−4, así que un correo que dice
"24 de julio, 21:05" corresponde a las 17:05 locales, y la regla de "dos alarmas el
mismo día" compara el día UTC. Dos alarmas a las 23:00 y a la 01:00 UTC son el
mismo día en Chile pero dos días distintos para el sistema. Se acepta a cambio de
que el correo diga exactamente lo que dice el reporte del fabricante.

### El diseño del correo: un ancho, tres colores

Se corrigió mirando un correo real ya enviado. Los bloques salían **cada uno con un
ancho distinto** —la tarjeta de EQUIPO angosta, la de alarmas ancha, la de
RECOMENDACIÓN más angosta todavía—, y eso no se lee como diseño, se lee como algo
roto.

La causa: las tablas declaraban `width: 100%; max-width: 660px` solo por CSS. El
motor de Word que usa Outlook **honra el atributo HTML `width`**, no ese CSS, así
que cada tabla colapsaba al ancho de su propio contenido. Ahora todas declaran
`width="660"` como atributo **y** como estilo. Hay un test que falla si alguna
queda con otro ancho.

Los colores salen del **manual de marca de Emeltec** (`Imagenes/MANUAL DE
MARCA_EMELTEC.pdf`, fuera del repositorio):

| Color | Origen | Para qué |
| --- | --- | --- |
| `#005f7f` | **PANTONE 7707C**, principal | La estructura: EQUIPO, QUÉ INDICA EL MONITOREO |
| `#98989a` | **PANTONE COOL GRAY 7C**, complementario | Reglas y texto secundario, en tintes |
| `#c00000` / `#a85400` | Convención, no marca | Gravedad: crítico y urgente |
| `#1e6b34` | Convención, no marca | La acción recomendada |
| `#4a4a4c` | Neutro de la familia del gris | La recomendación propia de Emeltec |

Cool Gray 7C no se usa a plena intensidad: sobre blanco da unos 3:1 de contraste,
por debajo del 4,5:1 que necesita el texto chico para leerse. Va como tinte claro
para las reglas (`#d9d9db`) y oscuro para el texto secundario (`#6b6b6d`).

Los colores de gravedad **no son de marca** y están declarados aparte a propósito:
el manual no define una paleta de severidad, y rojo/ámbar para niveles de alarma es
convención universal. Separarlos deja claro que señalan un nivel, no una identidad.

**El color corporativo es una sola línea**, `reports.brand_color` en
`config/settings.yaml`. Ambas plantillas derivan de ahí. Se dejó configurable en
lugar de clavado: así termina un documento imposible de rebrandear.

La tipografía del manual es **ANDIS**, que no existe en los clientes de correo. Se
queda Calibri con Arial de respaldo: una fuente que el lector no tiene se sustituye
sola por algo peor que una elección deliberada.

También se agregó aire —el espaciado interno pasó de 6px a 11–13px, y la separación
entre bloques de 14px a 22px— y encabezados de columna en la tabla de alarmas
(FECHA / TIPO / URGENCIA SEGÚN EL REPORTE), que antes no tenía.

### El trabajo del técnico nunca se pisa

Si el borrador ya tiene destinatario, o si el `[COMPLETAR]` fue reemplazado, se
considera editado: **no se toca**, y la alarma nueva va a un borrador aparte. Lo
mismo si ya fue enviado o borrado. Probado a propósito.

### La traducción, en tres capas

```
Frase entra
   ├─ 1. ¿Está en config/glossary.yaml?  -> esa manda     (anulación humana)
   ├─ 2. ¿Ya se tradujo antes?           -> de la caché   (gratis, idéntica)
   └─ 3. Nueva -> Gemini traduce -> SE GUARDA -> desde ahora es la 2
```

La capa 2 es la que hace esto confiable. Un servicio de traducción preguntado dos
veces puede responder distinto, y un cliente comparando el informe de enero con el
de marzo vería la misma condición descrita de dos formas. **Guardar la primera
respuesta elimina eso.**

La capa 1 existe para que el equipo pueda anular cualquier redacción que no les
guste, sin depender de nadie.

### Por qué Gemini y no Google Cloud para las frases

La facturación de Google Cloud **se trabó** (ver sección 5), y eso bloquea la
traducción del PDF. Pero una clave de **AI Studio es gratis y no pide tarjeta**, así
que las frases se traducen igual.

El nivel gratuito de Gemini usa los textos enviados para mejorar sus productos. Eso
es aceptable acá **solo por lo que realmente viaja**: una frase genérica de una
plantilla de Alfa Laval, sin cliente, planta, equipo ni número de serie. El diseño
ya aislaba el dato sensible, y esa decisión terminó destrabando el costo.

### El PDF adjunto queda en inglés

Traducirlo cuesta USD 0,08 por página y necesita la facturación de Google Cloud, que
está trabada. Se decidió avanzar sin eso: el informe en español del cuerpo lleva
todo lo que el cliente necesita para actuar.

Activarlo cuando la facturación se resuelva es cambiar `translation.provider` a
`"google"` en una línea. El código está escrito y probado.

---

## 3. Hallazgos técnicos que costaron trabajo

### El PDF no se puede leer por líneas

El texto plano pone las cuatro etiquetas de una fila en un renglón y los valores en
el siguiente, sin nada que indique cuál va con cuál. El parser lee por
**coordenadas**.

### pdfplumber no puede leer este PDF

La fuente del reporte tiene el mapa Unicode incompleto y pdfplumber devuelve NUL por
cada glifo sin mapear. `"Notification"` salía como `"Noti\x00cation"` y —esto es lo
grave— **el año `2026` salía como `202\x00`**. Todo el sistema de ventanas de 7 días
depende de esa fecha.

Se cambió a **PyMuPDF**, que resuelve esos glifos correctamente. Cero pérdidas.

### Dos etiquetas estaban mal configuradas

Las reales son **`Time Of Event (UTC)`** y **`Equipment Condition`**. Estaban como
"Event Time" y "Equipment Status", y con eso el informe salía sin fecha del evento y
sin estado del equipo.

### Las fechas son día-mes-año

Verificado contra el reporte real: `24-07-2026` es el 24 de julio, y el correo llegó
el 25. Si algún día llega un reporte con formato mes-día, hay que ajustar
`_DATE_FORMATS` en `src/clariot/store.py`.

### Un traductor automático genérico no sirve

Se probó un modelo local offline. `looseness` volvió como "carga", "seguridad",
"relajación" y "debilidad" en cuatro frases, y `misalignment` se convirtió en
**"malignación"**, que no existe.

Gemini con el vocabulario de Emeltec como contexto, en cambio:

| Inglés | Gemini |
| --- | --- |
| misalignment | Desalineación |
| looseness | Holgura |
| drive end | lado acople |
| non-drive end | lado libre |
| bearing wear | Desgaste de rodamiento |
| overall vibration | velocidad de vibración global |

### Los nombres de modelo de Gemini se retiran

`gemini-2.5-flash` devolvió *"no longer available to new users"*. Se usa el alias
**`gemini-flash-latest`**, que siempre apunta al vigente. Un modelo muerto detendría
la traducción en un PC que nadie administra, y la caché ya garantiza la consistencia
de las frases viejas.

### Contar correos habría sido un error

Los sistemas de alerta reenvían notificaciones. Se cuentan **eventos distintos**
—equipo más marca de tiempo del reporte— no correos. Dos correos del mismo evento se
reconocen como reenvío y no disparan una urgencia falsa.

Son dos protecciones en capas distintas: `ledger.db` evita procesar el mismo
**correo** dos veces; `events.db` evita contar el mismo **evento** dos veces.

### Un mensaje sin enviar siempre se guarda en Borradores

Outlook ignora la carpeta donde se creó. Hay que guardarlo y después moverlo.

### Gmail le pone Content-ID a todos los adjuntos

Había un filtro que descartaba adjuntos con Content-ID, para no confundir el logo
de una firma con un reporte. **Descartó un reporte real:** Gmail marca así todos
los adjuntos, PDFs incluidos, y la alarma se archivó como "sin PDF". El único
filtro es la extensión, y un logo de firma nunca es un PDF.

### Leer solo lo no leído hacía desaparecer alarmas

Un técnico que abre la alerta para mirar el adjunto la marca como leída. Con el
filtro de "no leído" esa alarma quedaba invisible para siempre — exactamente la
falla que el ledger existe para evitar. **Ahora se lee todo el correo de la
carpeta y el ledger decide** qué ya se procesó.

### Dos PDFs con el mismo nombre podían pisarse

El archivo se guardaba con un sufijo de marca de tiempo, y dos alarmas procesadas
en el mismo segundo colisionaban: el borrador de una podía terminar llevando el PDF
de otra. Ahora se compara el contenido y se busca un nombre libre. Verificado con
20 alertas: 20 archivos, 20 contenidos distintos, cero sobrescrituras.

---

## 3b. Lo que encontró la prueba de carga

20 alertas inyectadas de golpe en Outlook real (5 equipos × 4 días). Sacó a la luz
**tres bugs que ningún test unitario había tocado**, todos en el camino que más
importa: un equipo que alarma varias veces.

### El historial se filtraba por la fecha equivocada

Se pedía el historial del equipo desde "ahora menos 7 días", pero el clasificador
mide la ventana **desde la fecha del propio evento**. Una alarma que llegaba tarde,
o que pasaba unos días sin procesar, perdía su historial en silencio: tres alarmas
de la misma bomba parecían tres alarmas aisladas. Ahora se pasa el historial
completo del equipo y el clasificador aplica su ventana. La retención mantiene esa
lista corta.

### El enfriamiento degradaba el borrador abierto

Un informe sale solo si la gravedad sube — eso evita mandarle dos correos al
cliente por lo mismo. Pero al **reescribir** un borrador abierto se usaba el nivel
de la última alarma, y el enfriamiento lo bajaba a "normal": el `[URGENTE]` se
renombraba como informe de rutina y se movía fuera de `Urgencias`. La gravedad de
un borrador es ahora **la peor que alcanzó el equipo**, nunca la de la alarma que
llegó última.

### La consola contaba las acciones, no los borradores

El resumen decía `4 normales` en una corrida que había dejado cuatro borradores
`[URGENTE]`: la primera alarma de cada equipo era normal y el ascenso de la segunda
no corregía la cuenta. Esa línea es la que le dice al técnico **qué carpeta abrir**,
así que ahora describe los borradores como quedaron.

### Lo que mide la prueba

| | 12 alertas | 20 alertas |
| --- | --- | --- |
| Tiempo total | 7,9 s | 10,5 s |
| Por alerta | ~655 ms | ~523 ms |
| Borradores | 4 `[URGENTE]`, 3 PDFs cada uno | 5 `[URGENTE]`, 4 PDFs cada uno |
| PDFs archivados | 12 archivos, 12 contenidos | 20 archivos, 20 contenidos |

Se procesan **de a uno, en orden**. No hay hilos ni concurrencia: cada alerta se
archiva, se registra y se convierte en borrador antes de tocar la siguiente. Es
más lento que hacerlo en paralelo y es a propósito — el costo real no es el tiempo
de CPU sino el riesgo de que dos alarmas se cruzaran los adjuntos.

El arnés de la prueba vive fuera del repositorio, con bases de datos y carpetas de
Outlook desechables, y borra todo lo que creó. **Nunca toca el estado real.**

---

## 4. Los datos reales que ya tenemos

**El correo que llega:**

```
De     : Alfa Laval messaging system <support@aliotportal.com>
Para   : <la cuenta que recibe las alertas>
Asunto : Event notification report - VX-0000000
Fecha  : sábado 25 de julio, 02:11
```

Llegan a cualquier hora, incluso fin de semana. La regla va **por remitente**: el
asunto lleva el ID del sensor al final y el PDF se titula distinto
(`Event Report - 1st Notification`). El "1st" sugiere que hay seguimientos con otra
redacción, y una regla por asunto fallaría **en silencio** justo con las alarmas
repetidas.

**El reporte real:** 1 página, 2.699 caracteres, 433 palabras, 13 campos
extraídos. El nombre del equipo es exactamente `VX-RetCIPLin1 1206230`.

---

## 5. Lo que está pendiente

### Bloqueado: la facturación de Google Cloud

El registro de la tarjeta falló con **`OR_BACR2_44`**, un rechazo genérico del
sistema de pagos. Causas más probables, en orden:

1. La tarjeta tiene bloqueadas las compras internacionales (lo más común en Chile).
2. Es débito o prepago; Google pide crédito.
3. La dirección no coincide con la registrada en el banco.
4. Varios intentos seguidos empeoran el rechazo — esperar 24 h antes de reintentar.

**Conviene resolverlo con una tarjeta de la empresa**, no personal: al día 91 la
factura le llega a quien puso la tarjeta.

Esto **solo bloquea la traducción del PDF**. Todo lo demás funciona.

### Lo que se cerró el 28 de julio

- **El código está subido**, 56 archivos en `main`. Verificado contra el remoto que
  no viajó nada sensible: sin `Imagenes/`, sin `.env`, sin `state/`, sin `archive/`.
- **`state/`, `logs/` y `archive/` se generan solas** en la primera corrida.
  Comprobado con una copia limpia que solo tenía `src`, `config`, `templates` y
  `.env`: bastó un comando para que apareciera `state/events.db` con su esquema
  vacío. **No deben copiarse entre máquinas**: `ledger.db` es específico de cada
  buzón, y un Message-ID heredado marcaría una alarma real como ya procesada.
- **La caché de frases es local a cada máquina.** En el equipo del técnico arranca
  vacía, así que las primeras alarmas vuelven a preguntarle a Gemini; desde ahí la
  redacción queda congelada. Si algún día se corriera en dos equipos, las
  redacciones podrían divergir, y la solución sería copiar `events.db`, no
  rehacerlo.
- **Documentación y configuración quedaron sin datos identificables**: cero
  nombres de personas, cero correos, cero clientes, cero números de serie reales.
- **Código muerto eliminado:** `templates/alert_email.html.j2`, sobrante del diseño
  en que una alarma era un correo.

### Lo único que no se automatiza, en cualquier instalación

Verificado contra el código: **dos pasos son irreduciblemente humanos**, y el resto
es un comando.

| | Qué | Por qué |
| --- | --- | --- |
| 1 | Pegar la clave de Gemini en `.env` | Es un secreto: no viaja en el repositorio ni puede |
| 2 | Crear la regla de Outlook | No hay una línea en `src/` que toque la colección `Rules` del buzón. Se crea del lado del servidor, desde el navegador, para que funcione con el equipo apagado |

Las carpetas del buzón **sí** se crean solas con `--setup-folders`, y `state/`,
`logs/` y `archive/` aparecen en la primera corrida. En el disco no hay que crear
nada a mano.

Cuando algo falla después de instalar, el origen casi siempre es uno de esos dos.
Sin la clave, `--self-check` se detiene. Sin la regla, el programa corre sobre una
carpeta vacía **sin quejarse**, porque para él no tener alertas es una situación
normal — y eso es lo que lo hace difícil de diagnosticar.

### Estado del despliegue

Primera instalación completada en el equipo de un técnico: Outlook clásico, Python
3.12, el repositorio, el entorno virtual, las dependencias, la clave, las carpetas y
`--self-check` devolviendo `Todo listo`. La regla quedó creada.

Falta cerrar tres cosas, ninguna bloqueante:

1. **Probar que la regla mueve sola.** Hasta ahora los correos se movieron a mano, así
   que la regla está creada pero no demostrada. Se prueba marcando "Ejecutar regla
   ahora", o esperando la próxima alerta real.
2. **El acceso directo en el escritorio**, para que el uso diario no pida consola.
3. **La traducción del PDF**, cuando se resuelva la facturación. Es una línea:
   `translation.provider: "google"`.

Y una duda abierta de la primera corrida real: dos alertas del mismo equipo dejaron
un solo PDF adjunto. El caso se reprodujo en banco de pruebas con dos alarmas y los
dos PDF con el mismo nombre de archivo, y **adjuntó los dos**, así que el camino
funciona. Se resuelve mirando `archiveudit.csv`: si una fila dice `reenvio`, los
dos correos describían el mismo evento y el comportamiento fue el correcto.

### Limpieza hecha al cerrar

- **`--revisar-frases`** construido: lista lo que tradujo la IA para auditarlo y
  anularlo desde `glossary.yaml`.
- **`--preview` mostraba un correo distinto al real.** Usaba el armador viejo, de
  cuando una alerta era un correo. Ahora usa exactamente el mismo camino que la
  corrida real: lo que se ve es lo que el cliente recibiría.
- **`--dry-run` escribía en la base de eventos.** El ensayo hacía que la corrida
  real tratara la alarma como un reenvío ya contado, y no creaba el borrador. Lo
  encontró un test. Ahora un ensayo no deja rastro en ningún lado.
- **Código muerto eliminado:** `pipeline.py` y `email_builder.py`, reemplazados
  por `ingest.py`, `weekly.py` y `report_builder.py`. Tenían tests que los
  mantenían vivos artificialmente; esa cobertura se movió a `test_ingest.py`,
  contra el flujo real.
- **Documentación de código completa:** cero clases o funciones públicas sin
  docstring.
- **El estado de las pruebas quedó en cero.** Las bases `state/`, la carpeta
  `archive/`, los 12 mensajes `PRUEBA CLARIOT` en `Procesados` y los 4 borradores
  de prueba en `Por enviar` se borraron. Todo eso era data de prueba de esta
  sesión, no alarmas reales; el sistema arranca limpio.

---

## 5b. El repositorio es privado, y hay una razón legal

**No convertirlo en público sin resolver esto primero.**

El proyecto depende de **PyMuPDF, licenciado AGPL-3.0**. Es copyleft: quien
**distribuye** un programa que la usa queda obligado a publicar su propio código
bajo la misma licencia. Usarla dentro de la empresa no activa nada; un repositorio
público sí, porque publicar es distribuir.

| Situación | ¿Obliga el AGPL? |
| --- | --- |
| Uso interno, sin entregarlo a terceros | No |
| Repositorio **privado** | No |
| Repositorio **público** | Sí |
| Ofrecerlo como servicio en internet | Sí (por la "A" de Affero) |

Y no hay salida técnica: PyMuPDF está porque **pdfplumber no puede leer estos
PDF** —devolvía `202 ` en lugar de `2026`, lo que habría corrompido las ventanas
de 7 días en silencio—. Cambiar de librería no es una opción real.

Si algún día se quiere abrir, las salidas son dos: licenciar el repositorio como
AGPL-3.0, o comprarle a Artifex una licencia comercial de PyMuPDF. Conviene
consultarlo con la empresa, no resolverlo por intuición.

Por eso tampoco hay archivo `LICENSE`: siendo privado no hace falta, y poner uno
permisivo por costumbre sería justamente el error.

---

## 6. Cosas que conviene no olvidar

- **El programa nunca envía correo.** Por diseño, y no es configurable.
- Hay **tres cuentas** en juego, y conviene no confundirlas: la de **desarrollo**
  (el Outlook de pruebas), la del **técnico** (donde llegan las alertas y dónde se
  instala), y la del **administrador de Microsoft 365**. Las direcciones concretas
  no se anotan acá a propósito: este documento se versiona.
- **Outlook clásico únicamente.** El nuevo no expone COM. Microsoft lo retira de las
  suscripciones empresariales en 2028 y termina el soporte en abril de 2029; la
  migración a Graph afectaría **un solo archivo**,
  `src/clariot/adapters/outlook.py`.
- **Hay que activar el entorno** en cada terminal nueva:
  `.\.venv\Scripts\Activate.ps1`. `Procesar alertas.bat` no lo necesita porque llama
  al Python del entorno directo.
- `state/events.db` y `state/ledger.db` **no se editan a mano.**
- La clave de Gemini vive en `.env`, que está en `.gitignore`.
- Una bomba que alarma **cada 10 días no se agrupa**: la ventana es de 7 días,
  configurable en `grouping.window_days`.
- Los **gráficos de vibración no se traducen nunca**: son imágenes.
- El PDF de ejemplo `ejemplo clariot.pdf` **ya venía traducido por Google**. El real
  en inglés es `clariot original.pdf`.

---

## 7. Los documentos del proyecto

Ordenados por cuándo se leen, no por importancia:

| Si querés... | Leé | Qué es |
| --- | --- | --- |
| Entender qué hace esto | `README.md` | La puerta de entrada: qué resuelve, requisitos, instalación resumida, comandos y límites conocidos |
| **Instalarlo en un equipo** | **`DESPLIEGUE.md`** | El checklist: 11 pasos desde un equipo sin nada, cada uno con su verificación, y una tabla de síntomas y causas |
| Operarlo día a día, o algo falla | `INSTALACION.md` | El manual largo: el glosario, la traducción, el informe semanal, y 13 secciones de detalle |
| Saber por qué los informes son así | `PROPUESTA-INFORMES.md` | El razonamiento del diseño, con ejemplos del correo |
| Cambiar algo, o entender una decisión | `ESTADO.md` | Este documento |

**Regla para quien edite estos archivos:** el paso a paso vive en **un solo lugar**,
`DESPLIEGUE.md`, con una versión resumida en el README. No lo copies a un tercer
documento: tres copias se desincronizan, y a partir de ahí nadie sabe cuál es la
buena.
