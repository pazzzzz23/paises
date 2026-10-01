# CRUD de países

Aplicación web en Python para consultar, crear, editar y eliminar registros de la tabla `paises` en MySQL/MariaDB, dentro de la base `paises_7B`. La aplicación inspecciona las columnas directamente desde la base de datos, así que no requiere asumir nombres de campos; la tabla debe tener exactamente una clave primaria.

## Requisitos

- Python 3.10 o posterior.
- MySQL o MariaDB disponible en el equipo o servidor.
- Un usuario con permisos de lectura, inserción, actualización y eliminación en `paises_7B.paises`.

## Configuración y ejecución en Linux

1. Crea y activa un entorno virtual:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Instala las dependencias:

   ```sh
   pip install -r requirements.txt
   ```

3. Copia `.env.example` a `.env` y completa los datos reales de conexión:

   ```env
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_USER=tu_usuario
   DB_PASSWORD=tu_contraseña
   DB_NAME=paises_7B
   ```

   No compartas ni subas `.env` al repositorio. Si prefieres, configura `DATABASE_URL` con una URL `mysql+pymysql://...` en vez de las variables `DB_*`.

4. Desde esta carpeta, inicia el servidor:

   ```sh
   uvicorn main:app --reload
   ```

5. Abre <http://127.0.0.1:8000> para usar el panel. La documentación interactiva de la API está en <http://127.0.0.1:8000/docs>.

## Operaciones disponibles

- `GET /api/schema`: columnas y tipos detectados en `paises`.
- `GET /api/paises`: listar registros (`limit` y `offset` opcionales; máximo 500 por petición).
- `POST /api/paises`: crear un registro con un objeto JSON cuyas claves sean nombres de columnas.
- `PUT /api/paises/{id}`: actualizar columnas de un registro.
- `DELETE /api/paises/{id}`: eliminar un registro.

La clave primaria autoincremental se rellena automáticamente. Las restricciones y los campos obligatorios los determina el esquema ya existente en MySQL; este proyecto no crea ni modifica tablas.
