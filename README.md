# BlenderManager

Administra y gestiona tus versioens de blender. 


Para instalar pyinstaller:

pip install pypinstaller

apt-get install python3-dev

La primera vez usamos, esto genera un main.spec en mi caso lo copio y renombro a builder_lnx.spec, para tener un spec segun plataforma:
pyinstaller --onefile --windowed src/main.py

Pero si editamos el main.spec usaremos esto:
pyinstaller --onefile --windowed builder_lnx.spec 
