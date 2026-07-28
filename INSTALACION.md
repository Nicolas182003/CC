# Manual de instalación y operación

Documento operativo. Seguí los pasos en orden; cada uno se verifica antes de
pasar al siguiente.

---

## 1. Qué hace el programa

Lee las alertas que Clariot deja en una carpeta de Outlook y **deja un borrador
listo para revisar**. Nunca envía correo.

Cada borrador lleva:

- El **PDF original** adjunto.
- Un **informe en español** en el cuerpo: equipo, problema detectado, causa
  probable, acción recomendada y plazo.
- Un bloque **RECOMENDACIÓN DE EMELTEC** vacío, para que el técnico ponga su
  criterio antes de enviar.

El técnico completa el destinatario y el nombre del contacto, escribe su
recomendación, revisa y envía.

### ¿Arranca solo o es manual?

**Es manual, a propósito.** El técnico hace **doble clic** en un acceso directo
cuando se sienta a revisar correos.

La razón es técnica y no se puede evitar: el programa necesita que **Outlook esté
abierto**. Si corriera solo cada diez minutos con Outlook cerrado, fallaría cada
vez y llenaría el log de errores. Atándolo al momento en que la persona abre
Outlook, esa condición se cumple siempre.

**Las alertas no se pierden mientras el equipo está apagado.** La regla de Outlook
es del lado del servidor: los correos se archivan en la carpeta `Clariot` en
cuanto llegan y se acumulan sin leer. El programa los procesa todos juntos en la
siguiente corrida.

Si más adelante quieren que corra sin intervención, hay una alternativa
documentada en la sección 9, con sus condiciones.

### ¿Qué está automático y qué no?

| Parte | Estado |
| --- | --- |
| Leer el correo y el PDF | Automático |
| Agrupar alarmas por equipo y clasificar la gravedad | Automático |
| **Traducir las frases del informe al español** | **Automático, con IA (Gemini)** |
| Redactar el correo y adjuntar el PDF | Automático |
| Archivar el original y registrar la auditoría | Automático |
| **Traducir el PDF adjunto** | **No.** Queda en inglés. Ver sección 7 |
| Poner el destinatario y el nombre del contacto | **El técnico** |
| Escribir la recomendación de Emeltec | **El técnico** |
| Enviar | **El técnico** |

### La regla que decide la gravedad

| Situación | Asunto | Carpeta |
| --- | --- | --- |
| 2 o más alarmas del mismo equipo **el mismo día** | `[CRITICO]` | `Urgencias` |
| 2 o más alarmas del mismo equipo **en 7 días** | `[URGENTE]` | `Urgencias` |
| Urgencia declarada por el propio reporte | `[URGENTE]` | `Urgencias` |
| Alarma aislada | sin prefijo | `Por enviar` |

### Un solo borrador por equipo, que va creciendo

Esto es lo más importante de entender:

```
1ª alarma       -> borrador nuevo en "Por enviar", con 1 PDF
2ª alarma       -> EL MISMO borrador: 2 PDFs, pasa a "Urgencias" como [URGENTE]
3ª el mismo día -> EL MISMO borrador: 3 PDFs, pasa a [CRITICO]
```

El cliente recibe **un correo por equipo**, no uno por alarma. Pasados los 7 días,
la siguiente alarma arranca un borrador nuevo.

Y un informe sale **solo si la gravedad sube**. Sin esa regla, la cuarta alarma del
día generaría otro `[CRITICO]` y la palabra dejaría de significar algo.

**El programa nunca pisa el trabajo del técnico.** Si el borrador ya tiene
destinatario, o si el `[COMPLETAR]` ya fue reemplazado, se considera editado: no se
toca, y la alarma nueva va a un borrador aparte. Lo mismo si ya fue enviado o
borrado.

---

## 2. Qué hay que instalar

| Requisito | Detalle |
| --- | --- |
| Windows 10 u 11 | El equipo del técnico, no un servidor |
| **Outlook clásico de escritorio** | Con la cuenta donde llegan las alertas |
| Python 3.10 o superior | Marcar "Add Python to PATH" al instalar |
| Una clave de **Gemini** | Gratis, sin tarjeta. Ver sección 6 |

Las dependencias de Python se instalan solas con `requirements-dev.txt`:

| Paquete | Para qué |
| --- | --- |
| `pywin32` | Hablarle a Outlook |
| `pymupdf` | Leer el PDF. Licencia AGPL, sin problema para uso interno |
| `Jinja2` | Armar el cuerpo del correo |
| `PyYAML` | Leer la configuración |
| `python-dotenv` | Leer la clave desde `.env` |
| `pytest` | Correr los tests |

### Lo que NO hace falta

- **No** hace falta permiso de TI ni del administrador de Microsoft 365.
- **No** hay que registrar una aplicación en Azure AD.
- **No** se usa Microsoft Graph ni OAuth.
- **No** se guarda ninguna contraseña de correo.
- **No** hace falta tarjeta de crédito. La clave de Gemini es gratuita.

---

## 3. Cómo se conecta con Outlook

El programa **no se conecta a un servidor de correo**. Le habla al Outlook
instalado en el equipo, usando una interfaz de Windows llamada COM. Hereda la
sesión, los permisos y las carpetas del usuario. Por eso no necesita credenciales.

De ahí salen dos condiciones que no se pueden saltar:

1. **Tiene que ser el Outlook clásico.** El "nuevo Outlook" no ofrece esta
   interfaz. `python -m clariot --self-check` lo responde sin ambigüedad.
2. **Corre en el equipo donde está el buzón.** Lee el buzón **principal** de ese
   Outlook. Un buzón agregado como cuenta secundaria **no se lee**.

> Las alertas llegan al buzón **del técnico que las atiende**. El
> programa va instalado en su equipo, con su Outlook.

---

## 4. Instalar

Todo en **CMD** (`Windows + R`, escribir `cmd`, Enter), no en PowerShell:
PowerShell bloquea por defecto la ejecución de scripts y eso obliga a un permiso
extra que en CMD no hace falta.

```cmd
cd /d C:\clariot
python -m venv .venv
.venv\Scriptsctivate.bat
pip install -r requirements.txt
pip install -e .
```

El último comando es obligatorio: registra el proyecto para que
`python -m clariot` lo encuentre. Sin él vas a ver `No module named clariot`.

Para correr los tests, en lugar de `requirements.txt` usá
`requirements-dev.txt`, que agrega pytest.

**Hay que activar el entorno en cada ventana nueva** con
`.venv\Scriptsctivate.bat`. El prompt tiene que quedar así:

```
(.venv) C:\clariot>
```

**Si no aparece `(.venv)`, no sigas**: todo lo que instales después iría al Python
del sistema.

El acceso directo del escritorio **no necesita nada de esto**: llama al Python del
entorno directamente.

Verificá:

```cmd
python -m clariot --help
```

---

## 5. Preparar Outlook

### Las carpetas

Con Outlook abierto:

```cmd
python -m clariot --setup-folders
```

Crea las que falten:

```
Bandeja de entrada
├── Clariot          <- acá caen las alertas. Se acumulan si el programa no corre
└── Procesados       <- originales ya procesados

Borradores
├── Urgencias        <- 2+ alarmas: revisar y enviar hoy
└── Por enviar       <- alarma aislada: rutina
```

Los nombres se cambian en `config\settings.yaml`, sección `outlook`. **No hay que
tocar código.** Escribilos en el YAML exactamente igual que en Outlook, incluidos
los acentos.

Si preferís una sola carpeta de borradores, dejá `urgent_draft_folder: ""` y todo
cae en `Por enviar`, diferenciado por el prefijo del asunto.

> `Procesados` no puede estar dentro de `Clariot`. Si lo está, el programa se
> niega a arrancar y explica por qué.

### La regla

Creala **desde el navegador** (`outlook.office.com` → Configuración → Correo →
Reglas), para que quede del lado del servidor y funcione con el equipo apagado.

- Condición: **el remitente es** `support@aliotportal.com`
- Acción: **mover a** `Clariot`

**Por remitente, no por asunto.** El asunto real es
`Event notification report - VX-0000000`, con el ID del sensor al final, y el PDF
se titula `Event Report - 1st Notification`. Ya hay dos redacciones distintas para
lo mismo, y el "1st" sugiere que existen seguimientos con otra. Una regla por
asunto fallaría **en silencio** justo con las alarmas repetidas, que son las que
más importan.

Si llegan correos de ese remitente que no son alertas, no molestan: el programa
los archiva y los cuenta aparte como `sin PDF (no eran alertas)`.

---

## 6. La traducción de las frases

**Esto es lo que traduce el informe del cuerpo del correo al español.** El PDF
adjunto es otra cosa; ver sección 7.

Funciona en tres capas:

```
Frase entra
   ├─ 1. ¿Está en config\glossary.yaml?  -> esa manda      (anulación de Emeltec)
   ├─ 2. ¿Ya se tradujo antes?           -> de la caché    (gratis, instantáneo)
   └─ 3. Nueva -> Gemini la traduce -> SE GUARDA -> desde ahora es la 2
```

**La capa 2 es la que hace esto confiable.** Un servicio de traducción preguntado
dos veces puede responder distinto, y un cliente comparando el informe de enero
con el de marzo vería la misma condición descrita de dos formas. Guardar la
primera respuesta elimina eso: **cada frase se traduce una vez y se reutiliza
siempre.**

La capa 1 existe para que el equipo pueda **anular cualquier redacción** que no le
guste, sin depender de nadie.

### La clave de Gemini

Se saca en **`aistudio.google.com/apikey`** con una cuenta de Google. Es
**gratuita y no pide tarjeta de crédito**.

Copiá `config\env.example` a la raíz del proyecto como `.env` y poné:

```
GEMINI_API_KEY=AIza...tu-clave
```

`.env` está excluido del control de versiones. La clave no se sube a ningún lado.

### Por qué esto no expone datos del cliente

El nivel gratuito de Gemini usa los textos enviados para mejorar sus modelos. Es
aceptable acá **solo por lo que realmente viaja**:

```
"Potential impeller damage or imbalance."
```

Eso es todo. **Sin cliente, sin planta, sin equipo, sin número de serie, sin
fecha.** Es una frase genérica de una plantilla de Alfa Laval. Hay un test que
verifica que nada más sale.

### Revisar lo que tradujo la IA

```cmd
python -m clariot --revisar-frases
```

Lista cada frase traducida por la IA. Si alguna no les gusta, la escriben en
`config\glossary.yaml` bajo `phrases:` y esa versión manda desde ese momento.
**Nada queda sin control humano.**

### Por qué no un traductor automático común

Se probó un modelo local. `looseness` volvió como "carga", "seguridad",
"relajación" y "debilidad" en cuatro frases distintas, y `misalignment` se
convirtió en **"malignación"**, que no existe en español.

Gemini, con el vocabulario de la sección `terms:` de `glossary.yaml` como
contexto, devuelve: `misalignment` → **Desalineación**, `looseness` →
**Holgura**, `drive end` → **lado acople**, `non-drive end` → **lado libre**.

### Si Gemini falla

La frase queda sin traducir y **se reintenta en la próxima corrida** — el error no
se guarda en la caché. Según `glossary.on_missing`:

- `hold` (por defecto): **no se crea el borrador** hasta que la frase se resuelva.
  El cliente nunca recibe texto en inglés.
- `mark`: el borrador se crea con `[TRADUCIR]` en el asunto y un aviso rojo arriba
  que hay que borrar a mano antes de enviar.

Las alarmas **urgentes y críticas nunca se retienen** (`never_hold_urgent: true`):
demorar un aviso de seguridad por un diccionario sería peor. Esas salen con el
aviso rojo.

---

## 7. El PDF adjunto: por qué queda en inglés

Traducir el PDF conservando la maquetación cuesta dinero. La única opción viable
es Google Cloud Translation, a **USD 0,08 por página**, y estos reportes son de
una página.

**Está construido y probado, pero desactivado**, porque el registro de la tarjeta
en Google Cloud falló (`OR_BACR2_44`). Ver `ESTADO.md`, sección 5.

Para activarlo cuando se resuelva:

1. `pip install -r requirements-optional.txt`
2. En `.env`: `GOOGLE_CLOUD_PROJECT` y `GOOGLE_APPLICATION_CREDENTIALS`
3. En `config\settings.yaml`: `translation.provider: "google"`

Mientras esté en `"none"`, el informe del cuerpo lleva todo lo que el cliente
necesita para actuar, en español.

> Los **gráficos de vibración no se traducen nunca**, ni pagando: son imágenes,
> no texto. Por eso el resumen va en el cuerpo del correo.

---

## 8. Los comandos

| Comando | Qué hace |
| --- | --- |
| `python -m clariot` | **Operación normal.** Procesa las alertas nuevas |
| `python -m clariot --self-check` | Verifica Outlook, carpetas, clave y configuración |
| `python -m clariot --setup-folders` | Crea las carpetas de Outlook |
| `python -m clariot --preview PDF` | Muestra el informe de un PDF, sin tocar nada |
| `python -m clariot --revisar-frases` | Lista lo que tradujo la IA, para auditarlo |
| `python -m clariot --dry-run` | Recorre todo **sin escribir nada** |
| `python -m clariot --limit 1` | Procesa un solo correo |
| `python -m clariot --simulate PDF` | Inyecta una alerta de prueba, sin enviar correo |
| `python -m clariot --pending` | Lista lo retenido y lo que espera informe semanal |
| `python -m clariot --report` | Informe semanal por cliente (ver sección 10) |

---

## 9. Primera prueba, en cuatro escalones

No corras el programa completo de entrada.

### Escalón 1 — ¿lee bien el PDF?

```cmd
python -m clariot --preview "Imagenes\clariot original.pdf"
```

Muestra cada campo extraído y deja un `preview.html` que se abre en el navegador.
No toca Outlook.

### Escalón 2 — ¿está todo conectado?

```cmd
python -m clariot --self-check
```

Tiene que decir `Todo listo`.

### Escalón 3 — ¿qué haría, sin hacerlo?

```cmd
python -m clariot --dry-run
```

No crea borradores, no marca nada, no deja rastro.

### Escalón 4 — una alerta de prueba real

```cmd
python -m clariot --simulate "Imagenes\clariot original.pdf" --simulate-id "<prueba-1@aliot>"
python -m clariot
```

`--simulate` inyecta la alerta en la carpeta **sin enviar ningún correo**. Andá a
`Borradores\Por enviar` y revisá el resultado.

Para probar la acumulación, repetí con **otro** `--simulate-id` y un PDF con fecha
distinta: el borrador se actualiza en vez de duplicarse.

Al terminar, borrá los mensajes de prueba desde Outlook.

---

## 10. Cómo se dispara en el día a día

1. Clic derecho en **`Procesar alertas.bat`** → `Enviar a` → `Escritorio (crear
   acceso directo)`.
2. Cuando el técnico revisa correos: abre Outlook, doble clic en el acceso
   directo, espera.
3. La ventana le dice qué hizo. Se cierra apretando una tecla.
4. Revisa **`Borradores\Urgencias`** primero: eso se manda hoy.
5. Después **`Borradores\Por enviar`**: la rutina.
6. En cada borrador: escribe el destinatario, reemplaza `[NOMBRE]`, completa
   **RECOMENDACIÓN DE EMELTEC**, lee y envía.

Outlook **no permite enviar un correo sin destinatario**, así que un borrador a
medio terminar no puede salir por accidente.

### Alternativa: automático cada 10 minutos

Solo si el equipo queda **siempre encendido con Outlook abierto**.
`Programador de tareas` → `Crear tarea`:

- **General:** marcar *"Ejecutar solo cuando el usuario haya iniciado sesión"*.
  **NO** marcar *"Ejecutar tanto si el usuario inició sesión como si no"*: Windows
  la correría en una sesión aislada sin escritorio, donde Outlook no existe, y
  fallaría siempre.
- **Desencadenadores:** al iniciar sesión, repetir cada 10 minutos,
  indefinidamente.
- **Acciones:** iniciar `run.bat`, con "Iniciar en" apuntando a la carpeta del
  proyecto.

---

## 11. Opcional: informe semanal consolidado

Por defecto, **cada alarma aislada genera su propio borrador** al instante. Si un
cliente tiene 6 alarmas de 6 equipos distintos, recibe 6 correos.

Si preferís uno solo por cliente, en `config\settings.yaml`:

```yaml
reports:
  single_alarm: "weekly"
```

Las alarmas aisladas se acumulan, y el viernes:

```cmd
python -m clariot --pending    # ver qué hay acumulado
python -m clariot --report     # generar un informe por cliente
```

Las alarmas de urgencia siguen saliendo al instante.

---

## 12. Dónde mirar cuando algo falla

| Archivo | Qué contiene |
| --- | --- |
| `logs\clariot.log` | Todo lo que hizo, con la razón de cada decisión |
| `archive\audit.csv` | Una fila por alerta. Se abre en Excel (separador `;`) |
| `archive\AAAA-MM\` | Los PDFs originales, por mes |
| `state\events.db` | Las alarmas y la caché de frases. No editar a mano |
| `state\ledger.db` | Qué correos ya se procesaron. No editar a mano |

### Problemas frecuentes

**`No module named clariot`**
Falta `pip install -e .`, o el entorno no está activado. Mirá si el prompt dice
`(.venv)`.

**`Classic Outlook for Windows is not installed`**
Es el Outlook nuevo, o no hay Outlook. Ver sección 3.

**`Folder 'Clariot' not found`**
No existe o está escrita distinto. Corré `--setup-folders`.

**`GEMINI_API_KEY is empty`**
Falta la clave en `.env`. Ver sección 6.

**`El modelo ... fue retirado por Google`**
Poné `glossary.gemini_model: "gemini-flash-latest"` en `settings.yaml`. Es un
alias que siempre apunta al modelo vigente.

**`Se agoto la cuota gratuita de Gemini`**
Las frases quedan sin traducir y se reintentan solas en la próxima corrida. Nada
se pierde.

**¿Se pueden duplicar los borradores?**
No. Antes de procesar, el programa consulta `state\ledger.db` y saltea lo ya
hecho, usando el **Message-ID** del correo, que no cambia ni al mover el correo de
carpeta. Y el borrador se registra como hecho **en el instante en que se crea**.
Podés correrlo diez veces seguidas: la primera trabaja, las otras nueve no hacen
nada.

**Llegaron dos correos de la misma alarma**
Se detecta y no se cuenta dos veces. La clave es el equipo más la marca de tiempo
del reporte. Queda anotado como `reenvio` en la auditoría.

---

## 13. Límites conocidos

- **Una bomba que alarma cada 10 días no se agrupa.** La ventana es de 7 días,
  configurable en `grouping.window_days`.
- **El PDF adjunto queda en su idioma original.** Ver sección 7.
- **Los gráficos de vibración no se traducen nunca.** Son imágenes.
- **Las fechas se leen como día-mes-año.** Verificado contra un reporte real
  (`24-07-2026` es el 24 de julio). Si algún día llega uno con formato mes-día,
  hay que ajustar `_DATE_FORMATS` en `src\clariot\store.py`.
- **Si el correo trae más de un PDF**, se usa el primero y queda anotado en el log.
- **El programa nunca envía correo.** Por diseño, y no es configurable.
