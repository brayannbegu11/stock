# Respuesta del constructor a la ronda 15 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda15_verificacion_20260909T234333Z.json` (sha256 `fb2e9cb0…9674`), árbol congelado e íntegro. Veredicto de Astra: **rechazado**. Verificó las correcciones de la ronda 14 (R13-05, R14-03, R14-07, R14-08 completas; R09-03, R12-01, R13-01, R13-07, R14-01, R14-02, R14-04, R14-05, R14-06 parciales) y produjo 7 hallazgos nuevos (R15-01..R15-07: 4 altos, 3 medios).

**Salida:** todas las pruebas en verde (recuento en `README.md`); cada hallazgo tiene prueba nombrada. Las cifras de la muestra y de la demo no cambian.

## 1. Hallazgos y acción tomada

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R15-01 | alta | `Document` valida también `period_end` (fecha), `availability_quality` (miembro del catálogo; una cadena válida se convierte, otra cosa se rechaza) y `payload` (mapa). No queda ningún campo de `Document` ni de `Packet` sin tipo o catálogo. | `test_r14_01_r14_02_…` (casos R15-01) |
| R15-02 | alta | La verificación histórica comprueba procedencia, integridad y re-derivación, pero **no** el reloj de ingestión: en histórico la captura es posterior al corte por construcción (PIT-04, relojes separados). La ingestión ≤ corte y `first_seen_at` sólo se exigen en prospectivo, tanto en `build_packet` como en la readmisión. | ídem (caso R15-02: captura de 2026 para un corte de 2024 admitida en histórico, rechazada en prospectivo) |
| R15-03 | alta | Las acciones enteras disponibles para vender (`Lot.whole`), las fracciones pendientes (`unresolved_fraction`) y las enteras de la posición (`shares`) se calculan sobre la cantidad **exacta** (`Fraction`), nunca sobre la aproximación decimal: 1.000 − 10⁻²⁹ tiene 999 enteras y una fracción positiva. | `test_r15_03_r15_04_whole_shares_and_cash_rights_follow_the_exact_quantity` |
| R15-04 | alta | Los dividendos en efectivo se calculan sobre la cantidad exacta por propietario (3 TWD × 4.000/3 = 4.000 TWD), también tras ventas parciales. | ídem |
| R15-05 | media | `MarketData.data_version` es una huella del **contenido** (barras, derechos validados, capturas, altas/bajas y versión del calendario); cambiar cualquiera de ellos en memoria, aunque conserve identificadores, detiene al pronosticador. | `test_r14_06_r15_05_forecaster_refuses_a_market_whose_content_changed_underneath` (captura, barra, derecho y calendario) |
| R15-06 | media | La invalidación de la rentabilidad bruta se decide por lote: sólo la selección que tenía el valor en cartera en la fecha ex del derecho ambiguo la pierde; un lote nuevo del mismo valor comprado después conserva su bruto. La incertidumbre del patrimonio (reclamación) sigue siendo permanente. | `test_r15_06_r15_07_new_lots_keep_gross_returns_and_the_report_flags_uncertain_equity` |
| R15-07 | media | El informe markdown publica el patrimonio final como «≈ … TWD (contable, INCIERTO: …)» cuando hay reclamaciones ambiguas o marcas de valoración en la valoración final. | ídem |
| R09-03 / R13-01 / R14-01 (parciales) | alta | Absorbidos por R15-01. | — |
| R14-02 (parcial) | alta | Absorbido por R15-02. | — |
| R12-01 / R14-06 (parciales) | — | Absorbidos por R15-05. | — |
| R13-07 / R14-04 (parciales) | alta | Absorbidos por R15-03 y R15-04. | — |
| R14-05 (parcial) | alta | Absorbido por R15-06. | — |

## 2. Posiciones de Astra sobre P1..P5

- **P1 (rechazo).** Aceptado: `period_end` y `availability_quality` eran vías (R15-01) y la verificación histórica confundía relojes (R15-02). Ambos corregidos.
- **P2 (acepto con condiciones).** Mantenido: la reconstrucción histórica (verificada o no) no es evidencia prospectiva acreditada.
- **P3 (rechazo).** Aceptado: sobreventa e importes aproximados (R15-03, R15-04) y contaminación de lotes nuevos (R15-06) corregidos.
- **P4 (acepto con condiciones).** Condición atendida: el informe muestra el patrimonio final como incierto (R15-07).
- **P5 (rechazo).** Aceptado: la inmutabilidad del mercado se comprueba por contenido (R15-05).

## 3. Respuestas a las preguntas del revisor

1. **Inmutabilidad de `MarketData`.** La versión cubre ahora el contenido (barras, derechos, capturas, altas/bajas, calendario); una sustitución que conserve identificadores cambia la versión y el pronosticador rehúsa continuar. No se impide mutar el objeto en Python (no hay forma barata de hacerlo), pero ninguna mutación pasa desapercibida.
2. **Nota de vigencia en el informe 19.** Añadida (remite a los informes 20 y 21).

## 4. Abierto

- Adaptadores criptográficos OpenTimestamps / RFC 3161; registro de producción vacío.
- Catálogo de extractores reales; pronosticadores con LLM (L1/L2).
- Política de cierres sobrevenidos y su fuente oficial; versiones históricas del calendario y de los derechos.
- Adaptador de lotes menores; maestro histórico completo; emisor con TEJ.
- Fuente oficial por fecha para precios del universo (`MI_INDEX`, `dailyQuotes`): descarga en curso; sin dividendos históricos por esa vía.
- Congelamiento del protocolo (costes y rotación, dimensionado, tolerancia de exposición, `block_length`, liquidez, tablero de innovación). Decisión del usuario.
