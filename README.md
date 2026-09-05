# Control Servicios Casa - Guía de Integración de Clientes

Este repositorio contiene la aplicación de cobro de servicios (Luz, Gas, Agua) para apartamentos. Actualmente está en producción y configurada para la cuenta principal (**marlen**, admin_id: `1`).

Esta guía documenta el **flujo manual paso a paso** para integrar nuevos clientes y personalizar sus reglas de cobro en el backend ([app.py](file:///c:/Users/samur/Desktop/servicios%20casa/control-servicios-casa/backend/app.py)).

---

## 📋 Pasos para Agregar un Nuevo Cliente

### Paso 1: Crear el Administrador en la Base de Datos
Cada cliente nuevo debe tener un registro en la tabla `administradores`.
Podemos agregarlo corriendo un script temporal o insertándolo directamente en la base de datos de producción con la contraseña cifrada.

1. **Hash de la contraseña**: En Python se debe generar usando `generate_password_hash("su_contrasena")`.
2. **Registro**:
   ```sql
   INSERT INTO administradores (usuario, password) VALUES ('nombre_cliente', 'pbkdf2:sha256:...');
   ```
3. **Identificar su ID**: Toma nota del `admin_id` generado para ese cliente (por ejemplo, `id = 3`).

---

### Paso 2: Registrar sus Apartamentos
El cliente puede agregar sus apartamentos directamente desde la interfaz web en la ruta `/admin/apartamentos` una vez inicie sesión, o los podemos precargar en la tabla `apartamentos` asociados a su `administrador_id`.

---

### Paso 3: Personalizar las Reglas de Cobro en `app.py`
Cuando el cliente nos indique cómo desea cobrar sus recibos, adaptaremos los cálculos en el backend filtrando por su `session["admin_id"]`.

A continuación se muestran los puntos específicos a modificar en [app.py](file:///c:/Users/samur/Desktop/servicios%20casa/control-servicios-casa/backend/app.py):

#### A. Cobros de Luz (División del Aseo)
* **Ubicación**: En las funciones `cobros()` (línea ~227) y `editar_recibo()` (línea ~1050).
* **Código actual (Marlen - id 1)**:
  ```python
  valor_aseo_por_apto = round(float(recibo["valor_aseo"]) / 8, 2)
  ```
* **Cómo adaptarlo**:
  ```python
  if session["admin_id"] == 1: # Marlen
      valor_aseo_por_apto = round(float(recibo["valor_aseo"]) / 8, 2)
  elif session["admin_id"] == 3: # Cliente Nuevo (ejemplo: 5 apartamentos)
      valor_aseo_por_apto = round(float(recibo["valor_aseo"]) / 5, 2)
  else:
      # Valor por defecto
      valor_aseo_por_apto = 0.0
  ```

#### B. Cobros de Gas (Grupos y Distribución de Diferencia)
* **Ubicación**: En las funciones `cobros_gas()` (línea ~690), `lecturas_gas()` (línea ~798), y `editar_recibo_gas()` (línea ~1159).
* **Código actual (Marlen - id 1)**:
  Tiene 2 grupos específicos de apartamentos hardcodeados:
  ```python
  if grupo_actual == 1:
      numeros = ("101", "401", "402", "501")
  else:
      numeros = ("201", "202", "301", "302")
  ```
* **Cómo adaptarlo**:
  ```python
  if session["admin_id"] == 1: # Marlen
      if grupo_actual == 1:
          numeros = ("101", "401", "402", "501")
      else:
          numeros = ("201", "202", "301", "302")
  elif session["admin_id"] == 3: # Cliente Nuevo (no usa grupos, cobra todo junto o tiene otros números)
      numeros = ("101", "102", "201", "202", "301") 
  ```

#### C. Mensajes de WhatsApp personalizados
* **Ubicación**: En las funciones `whatsapp()`, `whatsapp_gas()` y `whatsapp_agua()`.
* **Cómo adaptarlo**: Si el nuevo cliente quiere cambiar el texto del mensaje enviado (por ejemplo, cambiar la fecha límite de pago o las palabras del mensaje), podemos condicionar la variable `mensaje` según el `session["admin_id"]`.

---

### Paso 4: Despliegue en Render
Una vez realizados los cambios en `app.py`:
1. Hacer commit de los cambios:
   ```bash
   git add backend/app.py
   git commit -m "feat: agregar reglas de cobro para cliente [nombre]"
   ```
2. Subir los cambios a GitHub:
   ```bash
   git push origin main
   ```
3. Render detectará el push y redesplegará la aplicación automáticamente con las nuevas reglas.
