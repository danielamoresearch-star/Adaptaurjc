# ADAPTA-ITS 8.1 — Publicación HTTPS (Render)

## Estado real

Se entrega un **paquete listo para cargar a un repositorio privado y desplegar**, pero **NO** está publicado, ni existe aún un enlace web público. No utilizar datos personales reales antes de las evaluaciones institucionales requeridas.

## Por qué no basta una web estática

La app tiene FastAPI, sesiones, SQLite, BKT, preguntas y exportación XLSX del grupo completo. Un host exclusivamente estático no ejecutaría el servidor ni almacenaría las respuestas.

## Pasos para el responsable de la instalación

1. Crea o conecta una cuenta de Render. Alternativamente conecta el plugin Render en ChatGPT para realizar el despliegue desde una conversación autorizada.
2. Crea un repositorio Git **privado** (por ejemplo, en GitHub) y sube exclusivamente los archivos del proyecto. No subas contraseñas, registros académicos, bases de datos ni ficheros XLSX.
3. En Render: **New → Blueprint** → conecta el repositorio y selecciona `render.yaml`.
4. El Blueprint configura **un servicio Python de pago**, región **Frankfurt** y disco persistente **5 GB** en `/var/data`.
5. Introduce una contraseña docente *nueva y exclusiva*, de **mínimo 14 caracteres**, en la variable segura `ADAPTA_TEACHER_PASSWORD` (no debe incluirse en `render.yaml` ni en Git).
6. Revisa el coste mensual y confirma la creación del servicio. El despliegue crea un dominio HTTPS único `https://...onrender.com`. No se puede conocer de antemano.
7. Accede al dominio real que muestre el panel Render y comprueba `/healthz`, acceso docente, invitaciones de estudiantes, seis preguntas diagnósticas y Excel.
8. Prueba con códigos ficticios y dispositivos Android/iPhone/PC/Mac antes de invitar a alumnos reales.
9. Para integrar desde el Aula Virtual, publica **solamente el enlace HTTPS**. La aplicación sigue siendo independiente.

## Salvaguardas antes de usar con estudiantes reales

- Evaluación de protección de datos y autorización institucional (RGPD/LOPDGDD), base jurídica, información a participantes, plazos de conservación y acuerdo de tratamiento con el proveedor.
- Acceso docente separado por asignatura y cohorte: la versión actual usa **una contraseña docente global** y permite ver todas las cuentas registradas en la instancia; NO apta para múltiples profesores sin separación de roles.
- Pruebas de penetración y accesibilidad; protección contra intentos masivos de inicio de sesión; endurecimiento de sesiones y recuperación de cuentas.
- Programar copias de seguridad *externas* cifradas y verificar su restauración, especialmente de `adapta.sqlite3` y los ficheros `-wal`/`-shm` mientras esté abierto; preferir la API de backup de SQLite o ventanas de mantenimiento.
- Considerar PostgreSQL administrado para una implantación multiinstancia y escalable. Este paquete utiliza SQLite con **un único proceso** y almacenamiento persistente.
- Calibrar BKT y validar psicométricamente las preguntas antes de inferencia académica.
- La selección de Frankfurt no garantiza por sí sola el cumplimiento normativo; revisar transferencias, subprocesadores y retención.

## Comprobaciones locales

```bash
pip install -r requirements.txt
export ADAPTA_TEACHER_PASSWORD='ELIGE_UNA_CLAVE_DE_14_O_MAS_CARACTERES'
uvicorn server:app --host 127.0.0.1 --port 8000
```

En Windows PowerShell: `$env:ADAPTA_TEACHER_PASSWORD='...'`.

## Dominio propio

Cuando el despliegue funcione puedes configurar un dominio propio, con DNS y TLS gestionados por Render, sujeto al dominio que controles. No uses `urjc.es` ni identidades institucionales sin autorización.

## Rendimiento

El frontend está preparado para navegadores móviles y de escritorio. El modo PWA requiere HTTPS en producción, y las peticiones de API necesitan conexión. Render ofrece HTTPS automáticamente para su dominio de servicio, pero la aplicación **todavía no está desplegada ni probada en ese dominio**.
