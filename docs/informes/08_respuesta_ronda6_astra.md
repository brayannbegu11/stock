# Respuesta del constructor a la ronda 6 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda6_verificacion_20260909T193901Z.json` (sha256 `c4ee4c2b…3ee5`), árbol congelado e íntegro. Veredicto de Astra: **rechazado**. Confirmó las 12 correcciones de la ronda 5 (varias con matices que se convirtieron en los hallazgos nuevos) y produjo 10 hallazgos (R06-01..R06-10: 8 altos, 2 medios).

**Salida:** todas las pruebas en verde (recuento en `README.md`); cada R06 tiene prueba nombrada.

## 1. Hallazgos y acción tomada

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R06-01 | media | Modelo de confianza precisado en `twlab/seals.py` y en §3 de este informe: la garantía es para consumidores por defecto dentro de un proceso de confianza; no cubre la mutación del entorno de importación. El registro pasa a `MappingProxyType` (sólo lectura). | `test_r06_01_trust_model_registry_is_read_only` |
| R06-02 | alta | El evaluador valida el sobre archivado contra el esquema del contrato (con el recibo tolerado como «asignado tras el sello») y exige `packet_hash`. | `test_r06_02_r06_03_r06_04_*` |
| R06-03 | alta | El plazo de registro se deriva del protocolo, no del archivo: corte semanal obligatorio; plazo archivado = 08:30 Taipei dentro de la semana objetivo, o igual al corte (semana sin sesiones → fin de la semana objetivo). Nunca `None`. | ídem |
| R06-04 | alta | Una corrida archivada con `status != selected` no puede ser observación válida. | ídem |
| R06-05 | alta | Sin calendario el validador comprueba: `week_id` derivado del corte; plazo, entrada y salida dentro de la semana objetivo; `registration_deadline_at` igual al plazo (semana válida) o al fin de la semana objetivo (sin sesiones); semana sin sesiones sin entrada ni salida. | `test_r05_11_*`, `test_r06_05_registration_deadline_cannot_extend_the_seal_window` |
| R06-06 | alta | `enter_basket` reserva la identidad de todos los puestos (`ledger.reserve_owner`) antes de operar, también para cestas vacías o fallidas. | `test_r06_06_empty_or_failed_basket_still_reserves_its_identity` |
| R06-07 | alta | Una venta FIFO sin propietario atribuye el ingreso de referencia al propietario de cada lote consumido. | `test_r06_07_fifo_sale_without_owner_attributes_proceeds_to_consumed_lots` |
| R06-08 | alta | Un propietario ya liquidado se marca `exited`/`liquidated` con su resultado; no es una salida bloqueada. | `test_r06_08_full_liquidation_before_exit_keeps_the_result` |
| R06-09 | alta | Un puesto `exited` con residuo se reintenta en salidas posteriores; si el residuo se ha convertido en lote entero, se vende y el resultado se actualiza. | `test_r06_09_residual_turned_round_lot_is_sold_on_retry` |
| R06-10 | media | La atribución de dividendos usa el valor de referencia sin redondear; el efectivo cobrado sí se redondea con la política declarada. La garantía documental dice ahora exactamente eso. | `test_r06_10_dividend_attribution_uses_the_unrounded_reference_value` |

## 2. Respuestas a las preguntas del revisor

1. **P2 como garantía de consumidores por defecto.** Sí: la formulación vigente es la de §3. Se distinguen tres niveles: consumidores del protocolo (`validate_prediction`, `block_bootstrap_mean`) con `allow_test_authorities=False`, que sólo aceptan sellos de producción y hoy no aceptan ninguno; API de bajo nivel (`RawStore.is_sealed`, `seal_info`), que calcula sellos de cualquier autoridad registrada y no debe usarse como puerta del protocolo; y el entorno de importación, que queda fuera del modelo.
2. **Recuperación del paquete y del calendario acreditados.** El sobre sellado contiene la predicción completa y el `packet_hash`; el evaluador valida la predicción contra el esquema, deriva la semana y el plazo de registro sólo del corte semanal y del protocolo, y compara con la observación. Lo que aún no hace es re-derivar el paquete completo (haría falta archivar el paquete con su calendario); queda declarado como pendiente.
3. **Identidad y flujos por propietario.** `owners_seen` reserva cada `week_id:rank` al entrar, con o sin compra; por propietario se acumulan cantidad (lotes), ventas brutas de referencia (incluidas las FIFO que consumen sus lotes) y dividendos declarados sin redondear; las liquidaciones previas y los reintentos de residuos se reflejan en el puesto.

## 3. Formulación vigente de P2

Con el código y el proceso de confianza sin alterar, el registro de producción (`twlab.seals.PRODUCTION_VERIFIERS`) vacío y `allow_test_authorities=False`, `validate_prediction` y `block_bootstrap_mean` rechazan todo sello de autoridad de prueba y, por tanto, toda evidencia `prospective_registered`. Con `allow_test_authorities=True` aceptan sellos de prueba y la etiqueta se conserva: ese modo es exclusivamente para pruebas y así se documenta. La mutación del entorno de importación (monkeypatch, sustitución de módulos) queda fuera de la garantía. Además, antes de habilitar producción hacen falta los adaptadores criptográficos y el archivo del paquete acreditado (pregunta 2).

## 4. Abierto

- Adaptadores criptográficos OpenTimestamps / RFC 3161 (`twlab/seals.py`).
- Archivo del paquete acreditado (con calendario) para que el evaluador lo re-derive por completo.
- Catálogo de extractores reales y prueba original/corrección sobre capturas.
- Adaptador de lotes menores (零股).
- Módulo de informe estadístico STA-02/03/05/06/07.
- Congelamiento del protocolo (T2, plazo de registro de semanas sin sesiones, redondeo de efectivo y valores pendientes): decisión del usuario.
