# BlenderManager

**Administra y gestiona tus versioens de blender.**  

**Para instalar pyinstaller:**  
pip install PyInstaller  
apt-get install python3-dev  

**La primera vez usamos, esto:**  
NOTA: esto genera un main.spec en mi caso lo copio y renombro a builder_lnx.spec, para tener un spec segun plataforma  
pyinstaller --onefile --windowed src/main.py  

**Pero si editamos el main.spec usaremos esto:**  
pyinstaller builder_lnx.spec  


**Los requisitos mínimos para que funciones el binario de linux:**  
Una distro con glibc 2.25

**Recomiendo usar Pycharm y virtualenvs, así no es necesario reinstalar kivy con el reinstalador.sh a nivel de sistema.**
