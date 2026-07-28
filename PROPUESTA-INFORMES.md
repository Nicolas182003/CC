# Propuesta: de reenvío diario a informes con análisis

**Estado: IMPLEMENTADO y probado contra Outlook real.** 142 tests en verde.
Fecha de la propuesta: 27 de julio de 2026

> Este documento conserva el razonamiento detrás del diseño. Para operar el
> sistema, usar `INSTALACION.md`. Para instalarlo, `DESPLIEGUE.md`.
>
> **Cambios respecto de esta propuesta original**, decididos durante la
> implementación:
>
> 1. **Las alarmas aisladas ya no esperan al viernes.** Cada una genera su
>    borrador al instante en `Por enviar`. El informe semanal consolidado sigue
>    disponible con `reports.single_alarm: "weekly"` y el comando `--report`.
> 2. **Un solo borrador por equipo, que va creciendo.** La segunda alarma no crea
>    otro correo: actualiza el borrador abierto, suma su PDF y lo mueve a
>    `Urgencias` si la gravedad subió. Así el cliente recibe un correo por equipo
>    y nunca recibe dos veces la misma alarma.
> 3. **Un informe sale solo si la gravedad sube.** Sin esto, la cuarta alarma del
>    día habría generado otro `[CRITICO]`, y la palabra dejaría de significar algo.
> 4. **Un borrador que el técnico ya editó nunca se reescribe.** Se detecta por el
>    destinatario o por el `[COMPLETAR]` ya reemplazado, y la alarma nueva va
>    aparte.

---

## 1. Qué cambia y por qué

Hoy el sistema traduce cada alerta y la reenvía. Eso no aporta ingeniería: el
cliente podría traducir el PDF solo.

La propuesta es dejar de reenviar y empezar a **analizar**. El cambio central es
que las alarmas se acumulan y se agrupan, y de ahí sale información que hoy nadie
ve: **cuántas veces alarmó cada equipo.**

Una bomba con cuatro alarmas en la semana es una conversación distinta a cuatro
bombas con una alarma cada una. Alerta por alerta, esa señal se pierde.

### Consecuencia que conviene notar

Este diseño **elimina el costo del proyecto**. El PDF se adjunta en su idioma
original y el análisis va en español en el cuerpo, tomado del glosario. No hace
falta ninguna API de traducción: ni Google Cloud, ni DeepL, ni tarjeta de crédito.

---

## 2. Regla de clasificación

Cada alarma que entra recibe un nivel, y el nivel decide por dónde sale.

| Patrón detectado | Nivel | Vía | Asunto |
| --- | --- | --- | --- |
| **2 o más eventos del mismo equipo en el mismo día** | Crítico | Urgencias, inmediato | `[CRÍTICO]` |
| 2 o más eventos del mismo equipo en 7 días | Urgente | Urgencias, inmediato | `[URGENTE]` |
| Urgencia crítica declarada por el propio reporte | Urgente | Urgencias, inmediato | `[URGENTE]` |
| Evento aislado | Normal | Informe semanal, viernes | sin prefijo |

**Ventana de agrupación: 7 días corridos.** Decidido.

### Por qué el mismo día es un nivel aparte

Dos alarmas el mismo día ya caen en urgencia por la regla de los 7 días, así que
no hace falta un disparador nuevo. Pero la diferencia importa:

- Lunes y viernes → problema **persistente**. Hay que ir a verlo.
- Dos veces en cuatro horas → el equipo se está **degradando ahora**.

No es lo mismo y no debería llegar con el mismo asunto. El nivel crítico además
copia a la lista `critical_cc` de `clients.yaml`, que ya existe.

### La trampa: eventos contra correos

Contar correos sería un error. Si Clariot reenvía la notificación de un mismo
evento —cosa que hacen los sistemas de alerta— dos correos generarían un falso
informe de urgencia por un solo problema real.

**Se cuentan eventos distintos, no correos.** La clave del evento es el equipo más
la marca de tiempo del propio reporte (`Hora del evento (UTC)`). Dos correos con la
misma marca de tiempo son el mismo evento: se archiva el segundo PDF y no se
vuelve a contar.

Esto es distinto del `ledger`, que evita procesar el mismo **correo** dos veces.
Acá se evita contar el mismo **evento** dos veces. Son dos protecciones en capas
diferentes.

Si un reporte llega sin marca de tiempo, se cuenta como evento propio y queda
anotado en el log: es preferible un informe de urgencia de más que perder una
alarma real.

### Qué se considera "el mismo equipo"

Se agrupa por **número de serie** (`202611-VX`), no por nombre. Los nombres se
escriben distinto entre reportes; el número de serie no cambia. Si un reporte no
trae número de serie, se usa el nombre del equipo normalizado.

El cliente también entra en la clave: mismo equipo **y** misma compañía.

### Límite conocido de la ventana de 7 días

Una bomba que alarma cada 10 días es un patrón real y **no se va a agrupar**. Sus
alarmas van a salir como eventos aislados en informes semanales distintos, y el
cliente no va a ver la repetición.

Queda anotado como limitación aceptada. Si con el tiempo aparece ese caso, la
ventana es un parámetro en `settings.yaml`: se cambia sin tocar código.

---

## 3. Los dos flujos

El programa se parte en dos comandos.

### `--ingest` — captura, corre seguido

Puede correr todos los días, o varias veces al día.

1. Lee las alertas nuevas de la carpeta `Clariot`.
2. Extrae los datos del PDF y **los guarda** en la base local.
3. Archiva el PDF en `archive/AAAA-MM/`.
4. Marca el correo como leído y lo mueve a `Procesados`.
5. **Evalúa la regla de clasificación.** Si corresponde urgencia, genera el
   borrador de urgencia en el momento.

No genera nada para las alarmas aisladas: quedan esperando el viernes.

### `--report` — informe semanal, se corre el viernes

1. Toma todas las alarmas guardadas y **no reportadas todavía**.
2. Las agrupa por cliente.
3. Genera **un borrador por cliente**, con sus PDFs originales adjuntos.
4. Marca esas alarmas como reportadas, para que no salgan dos veces.

Un cliente sin alarmas en la semana no recibe nada.

### Carpetas en Outlook

```
Borradores
├── Urgencias      <- borradores inmediatos, para revisar y enviar hoy
└── Por enviar     <- informes semanales del viernes
```

Separadas a propósito: el técnico tiene que poder ver de un vistazo qué es
urgente y qué puede esperar.

---

## 4. Contenido del informe de urgencia

Se emite cuando un equipo repite o cuando la urgencia es crítica. Incluye
**todas** las alarmas acumuladas de ese equipo, no solo la que disparó el aviso.

```
Asunto: [URGENTE] Bba retor CIP Buffer VX - 4 alarmas en 6 días

Estimado/a [NOMBRE],

Durante los últimos días hemos registrado alarmas reiteradas en uno de
sus equipos, y consideramos que requiere verificación en terreno.

┌─ EQUIPO ────────────────────────────────────────┐
│ Cliente          Cliente A                      │
│ Planta           Los Lagos                      │
│ Equipo           Bba retor CIP Buffer VX        │
│ N° de serie      202611-VX                      │
│ Tipo             Bomba centrífuga               │
└─────────────────────────────────────────────────┘

┌─ 4 ALARMAS ENTRE EL 21 Y EL 26 DE JULIO ────────┐
│ 26 jul 14:02   Holgura o instalación   3-5 días │
│ 24 jul 08:15   Holgura o instalación   3-5 días │
│ 22 jul 19:40   Desalineación           3-5 días │
│ 21 jul 20:14   Holgura o instalación   3-5 días │
└─────────────────────────────────────────────────┘

┌─ QUÉ INDICA EL MONITOREO ───────────────────────┐
│ El sistema ha detectado una posible holgura o   │
│ un problema de instalación. Las vibraciones     │
│ prolongadas dañarán la bomba.                   │
└─────────────────────────────────────────────────┘

┌─ ACCIÓN RECOMENDADA ────────────────────────────┐
│ Verifique visualmente el estado con la bomba en │
│ marcha. Asegúrese de que cada uno de los cuatro │
│ pies apoye de forma uniforme sobre el piso...   │
└─────────────────────────────────────────────────┘

┌─ RECOMENDACIÓN DE EMELTEC ──────────────────────┐
│ [COMPLETAR]                                     │
└─────────────────────────────────────────────────┘

Quedamos atentos a sus comentarios.
Equipo Emeltec Chile

Adjuntos: 4 reportes originales
```

### Sobre el bloque "Recomendación de Emeltec"

Es una propuesta mía y la que más valor comercial tiene. Va vacío, con
`[COMPLETAR]`, y **obliga al técnico a poner su criterio** antes de enviar.

Ahí está la diferencia entre reenviar lo que dice una máquina y dar un servicio de
ingeniería. Si te parece que agrega fricción, se saca — pero ese bloque es el
único lugar del informe donde aparece el conocimiento de Emeltec.

---

## 5. Contenido del informe semanal

Un borrador por cliente, con las alarmas aisladas de la semana.

```
Asunto: Informe semanal de monitoreo - Cliente A - Semana del 21 al 27 de julio

Estimado/a [NOMBRE],

Adjuntamos el resumen de las alarmas registradas en sus equipos durante
la semana.

7 alarmas en 6 equipos

┌─ EQUIPO ───────────────┬─ ALARMAS ─┬─ ÚLTIMO EVENTO ──┬─ PLAZO ──┐
│ Bomba 7 (SN-8891)      │     2     │ Desalineación    │ 3-5 días │
│ Bomba 12 (SN-4402)     │     1     │ Holgura          │ 3-5 días │
│ Bba CIP 3 (SN-1120)    │     1     │ Cavitación       │ 1 semana │
│ ...                    │           │                  │          │
└────────────────────────┴───────────┴──────────────────┴──────────┘

┌─ OBSERVACIONES DE EMELTEC ──────────────────────┐
│ [COMPLETAR]                                     │
└─────────────────────────────────────────────────┘

Adjuntos: 7 reportes originales
```

Los equipos ordenados por cantidad de alarmas, y después por urgencia.

Si un equipo ya salió en un informe de urgencia esa semana, **no se repite acá**.

---

## 6. Qué se construye y qué no se toca

| Componente | Cambio |
| --- | --- |
| Parser del PDF por coordenadas | **Ninguno** |
| Glosario | **Ninguno** |
| Adaptador de Outlook | **Ninguno** |
| Auditoría en CSV | **Ninguno** |
| Traducción del PDF | **Se elimina del alcance** |
| Almacén de alarmas | **Nuevo** |
| Clasificación y agrupación | **Nuevo** |
| Plantilla de urgencia | **Nueva** |
| Plantilla semanal | **Nueva** |
| Comandos `--ingest` y `--report` | **Nuevos** |

La parte que costó más trabajo —leer ese PDF que venía destrozado— no se toca.

---

## 7. Riesgos y decisiones abiertas

**La ventana de agrupación.** Ver sección 2. Necesita criterio de ingeniería.

**Un equipo que ya recibió informe de urgencia y sigue alarmando.** Propuesta: un
informe de urgencia por equipo por semana. Las alarmas posteriores se suman al
informe semanal bajo ese equipo, así no se pierde nada y no se le manda un correo
por día al cliente. Excepción: si una alarma posterior es crítica por sí misma,
genera su propio aviso.

**El viernes hay que acordarse de correr el informe.** El programa necesita
Outlook abierto, así que no puede correr solo de madrugada. Queda como doble clic
en un acceso directo, igual que hoy. Se puede agregar un aviso: si es viernes y
hay alarmas sin reportar, avisar al abrir.

**Alarmas de la semana anterior sin reportar.** Si un viernes nadie corre el
informe, esas alarmas quedan pendientes y salen el viernes siguiente, indicando el
período real cubierto. No se pierden.

**Un cliente que no está en `clients.yaml`.** El borrador se genera igual, sin
destinatario, y el técnico lo completa. Igual que hoy.

---

## 8. Configuración nueva que se agrega

```yaml
grouping:
  # Días para considerar que dos eventos del mismo equipo son el mismo problema.
  window_days: 7
  # Eventos del mismo equipo dentro de un mismo día calendario: nivel crítico.
  same_day_is_critical: true
  # Eventos del mismo equipo que disparan un informe de urgencia.
  urgent_threshold: 2
  # Un informe de urgencia por equipo cada tantos días, para no saturar al
  # cliente. Las alarmas posteriores se suman al informe semanal.
  urgency_cooldown_days: 7

reporting:
  # Día en que se espera correr --report. Solo para el aviso al abrir.
  weekly_day: "viernes"
```

---

## 9. Decisiones tomadas

| Punto | Decisión |
| --- | --- |
| Ventana de agrupación | **7 días** |
| Mismo día, distinta hora | **Nivel crítico**, carpeta de urgencias |
| Umbral de urgencia | 2 eventos del mismo equipo |
| Clave de agrupación | Número de serie; si falta, nombre normalizado |
| Conteo | **Eventos distintos**, no correos |
| Traducción del PDF | **Fuera de alcance.** Se adjunta el original |
| Destinatario | Lo pone el técnico, como hoy |

## 10. Pendiente de confirmar

1. ¿Va el bloque **"Recomendación de Emeltec"** con `[COMPLETAR]` en los dos
   informes?
2. ¿Un informe de urgencia por equipo cada 7 días es razonable, o preferís que
   cada alarma nueva reabra el aviso?
