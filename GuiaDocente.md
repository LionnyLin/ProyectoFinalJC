PROYECTO FINAL · ESTRUCTURAS DE DATOS

# **PROYECTO FINAL (Borrador)**

## **Simulación y visualización del comportamiento del flujo en la red de alcantarillado de Ciudad Bicentenario**

----

*<u>Bajo diferentes escenarios de intensidad de lluvia</u>*

Asignatura: Estructuras de Datos  
Lenguaje de programación: Python  
Modalidad: grupos de 2 o 3 estudiantes  
Aplicación: interfaz gráfica de usuario (GUI)  
Caso de estudio: Ciudad Bicentenario, Cartagena de Indias

Simulación de la red de alcantarillado de Ciudad Bicentenario

PROYECTO FINAL · ESTRUCTURAS DE DATOS

## 1. Descripción del proyecto

El proyecto consiste en desarrollar una aplicación de escritorio que permita representar, simular y visualizar el comportamiento del flujo de agua a través de la red de alcantarillado de Ciudad Bicentenario, Cartagena, considerando diferentes escenarios de intensidad de lluvia.

La infraestructura se representará mediante un grafo dirigido: los vértices corresponderán a las alcantarillas o pozos de inspección (*manholes*) y las aristas a las tuberías que los conectan. La red incluirá las conducciones que transportan el agua hasta el punto de descarga correspondiente a la PTAR de Punta Canoa.

Los estudiantes recibirán información predeterminada sobre la infraestructura, incluidas las características geométricas de las tuberías y sus capacidades máximas de transporte, calculadas previamente mediante la fórmula de Manning (ref). A partir de estos datos implementarán una simulación temporal y una visualización mediante colores.

## 2. Objetivo general

Desarrollar una aplicación informática en Python que permita simular y visualizar el comportamiento temporal del flujo de agua en la red de alcantarillado de Ciudad Bicentenario, mediante la representación de la infraestructura como un grafo dirigido y la aplicación de estructuras de datos y algoritmos para analizar diferentes escenarios de intensidad de lluvia.

## 3. Objetivos específicos

1. Representar la red mediante un grafo dirigido, identificando alcantarillas, pozos y tuberías.
2. Implementar estructuras de datos para almacenar, consultar y actualizar la información de la red.
3. Procesar los escenarios de precipitación suministrados para determinar los caudales de entrada.
4. Implementar una simulación temporal del desplazamiento del agua por las tuberías.
5. Calcular el porcentaje de utilización de la capacidad de cada tubería en diferentes instantes.
6. Desarrollar una interfaz gráfica que visualice la evolución del flujo mediante una escala de colores.
7. Identificar las tuberías que alcanzan o superan su capacidad máxima.
8. Comparar el comportamiento de la red bajo diferentes condiciones de precipitación.

## 4. Información suministrada por el docente

Todos los grupos trabajarán con la misma información de referencia, organizada en un archivo digital.

### 4.1. DataSetBicentenario.xlsx

#### 4.1.1 Source(s)

* Identificador de los nodos fuentes (alcantarilla).

#### 4.1.2 Sinks(s)

* Identificador de los nodos sumideros (punto final del sistema de alcantarillado).

#### 4.1.3 Pipe(s)

* Identificador único de la tubería.
* Identificadores del nodo inicial y del nodo final.
* Longitud (m), diámetro (m) y pendiente (m/m).
* Coeficiente de rugosidad de Manning.
* Capacidad máxima de transporte (m<sup>3</sup>/s).
* Longitud (m).

Simulación de la red de alcantarillado de Ciudad Bicentenario

PROYECTO FINAL · ESTRUCTURAS DE DATOS

### 4.1.4 Drainage Basin

* Área de drenaje (hectáreas, ha).
* Coeficiente de escorrentía (adimensional).

### 4.1.5 Precipitation Scenarios

* Describe cada escenario de lluvia.

Las capacidades máximas serán suministradas por el docente y habrán sido calculadas previamente mediante la ecuación de Manning. Los valores definitivos, la duración de cada evento y los perfiles temporales de precipitación serán establecidos por el docente. Estos valores son escenarios académicos ilustrativos; no representan necesariamente registros históricos de Cartagena.

# 5. Fundamentos del modelo de simulación

## 5.1. Representación de la red

* Los vértices representan alcantarillas o pozos de inspección.
* Las aristas dirigidas representan las tuberías.
* La dirección indica el sentido previsto de circulación del agua.
* Cada arista almacena los atributos geométricos e hidráulicos de la tubería.

La representación computacional deberá corresponder a las conexiones reales incluidas en los archivos del docente.

## 5.2. Estimación del caudal generado por la lluvia

Para estimar el caudal de escorrentía asociado a cada área de drenaje se utilizará el método racional:

$$Q = 0.00278 \cdot C \cdot I \cdot A$$

Donde:

* $Q$: caudal de escorrentía (m<sup>3</sup>/s).
* $C$: coeficiente de escorrentía (adimensional).
* $I$: intensidad de precipitación (mm/h).
* $A$: área de drenaje (hectáreas).

El caudal calculado se incorporará al modelo en la alcantarilla correspondiente. Si se dispone de información sobre el caudal sanitario en tiempo seco, podrá incorporarse como componente adicional.

## 5.3. Capacidad máxima de transporte

La capacidad máxima de cada tubería será un dato de entrada suministrado por el docente, calculado previamente mediante Manning:

$$Q_{max_{u,v}} = \frac{1}{n} A R_h^{2/3} S^{1/2}$$

Donde $n$ es el coeficiente de rugosidad, $A$ el área hidráulica, $R_h$ el radio hidráulico y $S$ la pendiente hidráulica. Los estudiantes no deberán recalcular las capacidades máximas; deberán utilizarlas para evaluar el comportamiento de las tuberías.

Simulación de la red de alcantarillado de Ciudad Bicentenario

PROYECTO FINAL · ESTRUCTURAS DE DATOS

## 5.4. Simulación del transporte del agua

La simulación representará el desplazamiento del agua desde los puntos de entrada hacia los pozos de inspección, siguiendo las conexiones de la red. Se trabajará con intervalos discretos de tiempo; por ejemplo, actualizaciones cada minuto.

$$t_i = \frac{L_i}{V_i}$$

Donde $t_i$ es el tiempo estimado de tránsito, $L_i$ la longitud de la tubería y $V_i$ la velocidad de referencia. La velocidad de referencia será suministrada por el docente o definida a partir de los parámetros disponibles y los supuestos del modelo. El algoritmo deberá gestionar el tiempo de desplazamiento; no deberá suponer que el agua llega instantáneamente al siguiente nodo.

En los puntos donde converjan varias tuberías se acumularán los caudales recibidos. Cuando existan varias tuberías de salida, se aplicará la regla de distribución definida para el ejercicio. El docente suministrará o establecerá reglas comunes para todos los grupos.

## 5.5. Porcentaje de utilización de las tuberías

En cada intervalo de tiempo se calculará el porcentaje de utilización de la capacidad máxima:

$$O_i(t) = \frac{Q_i(t)}{Qmax_i} \times 100$$

Donde $O_i(t)$ es el porcentaje de utilización, $Q_i(t)$ el caudal transportado y $Qmax_i$ la capacidad máxima de la tubería. Ejemplo: si una tubería tiene capacidad máxima de 0.08 m<sup>3</sup>/s y transporta 0.06 m<sup>3</sup>/s, su utilización es (0.06 / 0.08) × 100 = 75 %.

Si el caudal supera la capacidad máxima, el programa deberá identificar y registrar la sobrecarga. El exceso no deberá desaparecer del modelo: se tratará de acuerdo con las reglas simplificadas de almacenamiento o acumulación establecidas para la simulación.

**Importante:** este indicador mide la utilización de la capacidad de transporte, no el porcentaje de llenado físico de la sección transversal. El llenado físico requiere un modelo adicional de profundidad y geometría hidráulica.

## 6. Requisitos funcionales

**RF01. Carga de información:** Cargar los archivos suministrados por el docente.

**RF02. Construcción del grafo:** Construir la red a partir de la información de alcantarillas, pozos de inspección y tuberías.

**RF03. Visualización:** Mostrar alcantarillas, pozos de inspección y tuberías, respetando las conexiones y las coordenadas disponibles (si son suministradas).

**RF04. Selección de escenario:** Permitir seleccionar cualquiera de los escenarios de precipitación.

**RF05. Configuración temporal:** Establecer la duración de la simulación y el intervalo de actualización.

**RF06. Ejecución temporal:** Actualizar los estados de las tuberías conforme avanza el tiempo.

**RF07. Escala de colores:** Representar el porcentaje de utilización mediante colores.

**RF08. Consulta:** Mostrar los atributos y el estado temporal de una tubería seleccionada.

**RF09. Control temporal:** Permitir iniciar, pausar y reanudar la simulación y consultar instantes anteriores.

**RF10. Tuberías críticas:** Identificar las tuberías con mayor utilización y las que superan su capacidad.

**RF11. Comparación:** Permitir comparar resultados de diferentes escenarios.

**RF12. Reporte:** Generar un reporte de escenarios, tiempos, tuberías críticas, caudales y utilización.

Simulación de la red de alcantarillado de Ciudad Bicentenario

PROYECTO FINAL · ESTRUCTURAS DE DATOS

## 7. Escala de colores

<table><thead><tr><th>Utilización</th><th>Color sugerido</th><th>Estado</th></tr></thead><tbody><tr><td>0–25 %</td><td>Verde</td><td>Baja utilización</td></tr><tr><td>>25–50 %</td><td>Amarillo</td><td>Utilización moderada</td></tr><tr><td>>50–75 %</td><td>Naranja</td><td>Utilización alta</td></tr><tr><td>>75–100 %</td><td>Rojo</td><td>Cercana a la capacidad máxima</td></tr><tr><td>>100 %</td><td>Rojo oscuro</td><td>Capacidad excedida</td></tr></tbody></table>

## 8. Estructuras de datos y algoritmos obligatorios

<table><thead><tr><th>Estructura</th><th>Aplicación</th></tr></thead><tbody><tr><td>Grafo</td><td>Representación de la red de alcantarillado.</td></tr><tr><td>Lista de adyacencia</td><td>Almacenamiento de conexiones entre nodos.</td></tr><tr><td>Cola</td><td>Procesamiento de nodos o eventos en recorridos y simulación.</td></tr><tr><td>Pila</td><td>Implementación de DFS y reconstrucción de caminos.</td></tr><tr><td>Tabla hash</td><td>Consulta de nodos y tuberías mediante identificadores.</td></tr><tr><td>Lista enlazada</td><td>Historial de estados o eventos de simulación.</td></tr></tbody></table>

Se deberán implementar, como mínimo, los siguientes algoritmos:

9. BFS (Breadth-First Search): recorrido de la red en amplitud.
10. DFS (Depth-First Search): recorrido de la red en profundidad.
11. Búsqueda y consulta de alcantarillas, pozos de inspección y tuberías.
12. Actualización temporal: procesamiento de eventos y estados del transporte del agua.
13. Identificación y clasificación de tuberías críticas según su porcentaje de utilización.

Las estructuras de datos y los algoritmos centrales deberán ser implementados por los estudiantes; no se permitirá delegar su funcionamiento en bibliotecas externas. Se podrán usar bibliotecas para la interfaz, lectura de archivos y visualización. Si se utiliza NetworkX, deberá limitarse a representación o análisis complementario, sin sustituir el grafo propio.

## 9. Interfaz gráfica

Se recomienda utilizar Tkinter o PySide6. La interfaz deberá incluir:

* Visualización del grafo de la red.
* Leyenda de colores.
* Selector de escenarios de lluvia.
* Controles para iniciar, pausar y reanudar la simulación.
* Indicador del tiempo transcurrido.
* Información de la tubería seleccionada.
* Tabla de tuberías críticas.
* Resumen de resultados del escenario.

La representación deberá permitir observar cómo cambia el estado de las tuberías conforme avanza la simulación.

## 10. Resultados esperados

14. Cargar y representar correctamente la red.
15. Ejecutar la simulación para los escenarios de precipitación suministrados.
16. Visualizar la evolución temporal mediante cambios de color en las tuberías.
17. Consultar porcentajes de utilización en distintos instantes.
18. Identificar tuberías que alcanzan o superan su capacidad máxima.
19. Comparar resultados entre escenarios.

Simulación de la red de alcantarillado de Ciudad Bicentenario

PROYECTO FINAL · ESTRUCTURAS DE DATOS

20. Identificar condiciones de mayor exigencia para la infraestructura.
21. Presentar resultados hasta el punto de descarga de Punta Canoa.

## 11. Validación de la aplicación

Los estudiantes deberán realizar pruebas para verificar, como mínimo:

* Correcta construcción del grafo y correspondencia con los archivos.
* Funcionamiento de BFS y DFS.
* Correcta incorporación de caudales de entrada.
* Actualización de los estados en cada intervalo.
* Cálculo correcto del porcentaje de utilización.
* Identificación de condiciones de sobrecarga.
* Coherencia del balance de caudales y volúmenes en los puntos de conexión.
* Consistencia al repetir un mismo escenario.

La aplicación deberá documentar los supuestos para estimar tiempos de tránsito, distribuir caudales y gestionar sobrecargas.

## 12. Requisitos técnicos

* Lenguaje de programación: Python.
* Interfaz gráfica: Tkinter o PySide6.
* Archivos de entrada en formato CSV.
* Representación de la red mediante un grafo dirigido (NetworkX).
* Código organizado en módulos y funciones.
* Identificadores únicos para alcantarillas, pozos de inspección y tuberías.
* Validación de datos y manejo de errores en la carga de archivos.
* Documentación básica del código.

Se podrán utilizar bibliotecas como Matplotlib para apoyar la visualización, sin sustituir las implementaciones propias exigidas.

## 13. Entregables

**Código fuente:** Proyecto completo en Python, organizado y comentado.

**Aplicación funcional:** Interfaz gráfica que permita cargar los datos y ejecutar los escenarios.

**Documento técnico:** Introducción, diseño, estructuras de datos, algoritmos, modelo de simulación, resultados, pruebas, conclusiones y limitaciones.

**Evidencias:** Capturas de pantalla de la red, evolución temporal, consulta de tuberías y resultados.

**Sustentación:** Presentación y demostración funcional ante el docente.

## 14. Criterios de evaluación

<table><thead><tr><th>Criterio</th><th>Porcentaje</th></tr></thead><tbody><tr><td>Representación de la red mediante grafos y estructuras de datos</td><td>20 %</td></tr><tr><td>Implementación de BFS, DFS y consultas</td><td>15 %</td></tr><tr><td>Simulación temporal y procesamiento de caudales</td><td>25 %</td></tr><tr><td>Cálculo de utilización y detección de sobrecargas</td><td>15 %</td></tr><tr><td>Interfaz gráfica y visualización por colores</td><td>10 %</td></tr><tr><td>Pruebas, validación y consistencia</td><td>10 %</td></tr><tr><td>Documentación y sustentación</td><td>5 %</td></tr></tbody></table>

Simulación de la red de alcantarillado de Ciudad Bicentenario

PROYECTO FINAL · ESTRUCTURAS DE DATOS

<table><tr><td>TOTAL</td><td>100 %</td></tr></table>

## Niveles de desempeño

**Nivel satisfactorio – hasta 4.0.** Representa correctamente el grafo, implementa las estructuras y algoritmos requeridos y ejecuta una simulación temporal básica.

**Nivel destacado – hasta 4.5.** Además, presenta una simulación consistente, interfaz funcional, consultas, identificación de tuberías críticas y validación de resultados.

**Nivel avanzado – hasta 5.0.** Cumple integralmente los requisitos y presenta mejoras técnicamente justificadas, como una distribución más elaborada del flujo, gestión de eventos mediante cola de prioridad, almacenamiento temporal en pozos de inspección, mejor tratamiento de tiempos de tránsito, visualización avanzada o validación adicional de conservación de masa.

La calificación dependerá de la calidad, corrección y sustentación. Las funcionalidades adicionales no compensarán errores en los requisitos fundamentales.

## 15. Consideraciones y alcance del modelo

* El proyecto tiene un propósito académico y se orienta a la aplicación de estructuras de datos y algoritmos.
* No se exige desarrollar un simulador hidráulico profesional ni resolver las ecuaciones completas de Saint-Venant.
* Las capacidades máximas de las tuberías serán suministradas por el docente.
* Los escenarios de precipitación serán predeterminados.
* Los tiempos de tránsito y las reglas de distribución se definirán mediante datos y supuestos comunes.
* Los resultados describen el comportamiento del modelo computacional y no constituyen un diagnóstico hidráulico certificado de la infraestructura real.

Se valorará que los estudiantes comprendan la relación entre la estructura del grafo, el procesamiento temporal, las estructuras de datos y la visualización de resultados.

## Resultado esperado

Una aplicación que permita observar cómo evoluciona el comportamiento de la red de alcantarillado de Ciudad Bicentenario ante diferentes escenarios de lluvia, identificando visualmente las tuberías con mayores niveles de utilización y aquellas que superan su capacidad de transporte.

Simulación de la red de alcantarillado de Ciudad Bicentenario

PROYECTO FINAL · ESTRUCTURAS DE DATOS

Anexo 1.- Modelo Alcantarillado Ciudad Bicentenario (enlace)

Plano del modelo de alcantarillado de Ciudad Bicentenario con zonas UE 1 a UE 7, red existente y proyectada, y cuadro de título M-7B (escala 1:5000, junio de 2012)

Simulación de la red de alcantarillado de Ciudad Bicentenario
12

PROYECTO FINAL · ESTRUCTURAS DE DATOS

# Anexo 2.- Grafo Dirigido (Paper submitted to OPSearch)

Directed graph of the sewer network of Ciudad Bicentenario with nodes labeled 1–31, edges labeled P1–P59 with weights, source nodes marked (S) and the terminal node 31 (T)

Simulación de la red de alcantarillado de Ciudad Bicentenario