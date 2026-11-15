# MICRO ADAPTA-ITS — Paso a piloto docente con datos duraderos

## Alcance de la comprobación (15-11-2026)

Servicio Render existente: `Adaptaurjc`, ID `srv-dbsae1mi0phs73cj4iug`, región Oregon, plan starter, una instancia. Aplicación: https://adaptaurjc.onrender.com.

La consulta de configuración del servicio NO proporciona evidencia de un disco persistente. La existencia de `render.yaml` en GitHub no acredita que ese Blueprint se haya aplicado al servicio existente. La base SQLite se guarda por defecto en `adapta_v6.sqlite3` dentro del árbol de la aplicación, que es efímero en Render salvo montaje explícito.

**No autorizar recogida de datos reales ni efectuar despliegues con datos no respaldados hasta solucionar la persistencia.**

## Migración segura del servicio existente (intervención del propietario)

1. Entrar en https://dashboard.render.com/web/srv-dbsae1mi0phs73cj4iug y abrir el panel docente de MICRO ADAPTA-ITS.
2. Descargar **Descargar copia de seguridad**; verificar que el archivo empieza por `SQLite format 3` y conservarlo de forma cifrada, con acceso restringido. Descargar también el Excel de investigación y verificar que sus totales coinciden con las métricas del panel. No almacenar copias con datos personales en GitHub ni en un repositorio público.
3. Detener las nuevas incorporaciones y pruebas. Preparar una ventana de mantenimiento y verificar el plan de facturación (los discos persistentes tienen coste adicional).
4. En el servicio ya existente de Render, abrir **Disk** y añadir un disco con ruta de montaje `/var/data` y el tamaño mínimo suficiente. No crear un segundo servicio ni aplicar ciegamente el `render.yaml`, que puede crear otro servicio y utiliza una región diferente.
5. Configurar la variable de entorno `ADAPTA_DB=/var/data/adapta.sqlite3` en el **mismo servicio**. Un cambio de variable o la incorporación del disco desencadenan un despliegue: realizarlo únicamente tras conservar y verificar la copia de seguridad.
6. Si existen registros previos, **restaurar la copia verificada** en el nuevo volumen con un procedimiento supervisado antes de reabrir el acceso. No comenzar con una base vacía ni sobrescribir registros existentes. La aplicación no realiza esa restauración automáticamente.
7. Comprobar en el panel docente que **Almacenamiento persistente** está verificado y que el conteo de estudiantes, preguntas, intentos, notas y sesiones coincide con la copia previa. Confirmar mediante un reinicio controlado y un segundo respaldo.
8. Establecer copias de seguridad externas cifradas, pruebas de restauración periódicas, política de retención y control de acceso. El disco persistente y las instantáneas diarias no sustituyen un respaldo independiente.

Fuente técnica: https://render.com/docs/disks

## Pruebas automatizadas ya incorporadas

- `python test_micro_quality.py`: acceso docente/alumnado, caducidad a 15 minutos, permisos, Excel de investigación, indicador de almacenamiento y recuperación de SQLite.
- `python test_browser_responsive.py`: navegación en motores Chromium y WebKit con tamaños de pantalla de Android, iPhone, tableta y ordenador; sin necesidad de credenciales ni datos reales.
- GitHub Actions: `.github/workflows/quality.yml` y `.github/workflows/browser_quality.yml`.

**Limitación:** el navegador WebKit ejecutado en CI no equivale a un iPhone físico. Para la aceptación final realizar una matriz de pruebas manuales con Safari iOS, Chrome Android, Safari macOS, Chrome/Edge Windows, lectores de pantalla y teclado.

## Validación científica del modelo de aprendizaje

El sistema aplica un estimador Bayesian Knowledge Tracing (BKT) desde el primer intento. La red MLP (16 y 8 neuronas ocultas) está condicionada a suficiente evidencia, estudiantes de entrenamiento y validación disjuntos, y mejora predictiva frente a un predictor base y BKT. El panel docente incorpora **Auditar modelo bayesiano y neuronal**.

La validación de **corrección de la respuesta futura** (log-loss, puntuación de Brier) no demuestra que las probabilidades representen correctamente el conocimiento latente. Hacen falta ítems ancla calibrados, pruebas externas, análisis de sensibilidad y estabilidad por asignatura/grado.

No atribuir causalidad a la variación de los posteriores ni a las métricas de actividad. Para evaluar el efecto de la plataforma sobre el rendimiento deben preservarse los grupos A/C control y B/D tratamiento, la asignación previa, la validez del instrumento y una estrategia de análisis preespecificada.

## Criterios mínimos de aceptación para el piloto

- Disco persistente verificado y datos preservados tras reinicio.
- Backup cifrado y prueba de restauración.
- Acceso/logout/expiración en 15 minutos comprobados en equipo real.
- Diagnóstico inicial de una cuestión por unidad, sin adelantarse la práctica.
- Bancos revisados por docente, especialmente las preguntas paramétricas de Microeconomía II.
- Cero errores críticos en CI y prueba de navegadores.
- Consentimiento/información al alumnado, minimización y base jurídica del tratamiento, y revisión de protección de datos conforme al protocolo institucional.
- Control periódico del tiempo de respuesta del servidor y capacidad en la instancia de 512 MB.
- Revisión ética y plan de análisis econométrico aprobados antes de emplear los datos para publicaciones.

**Estado:** los cambios de código y las pruebas automáticas no constituyen por sí solos certificación institucional, validación científica del modelo ni acreditación de persistencia.
