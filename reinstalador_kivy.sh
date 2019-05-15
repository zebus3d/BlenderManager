#!/bin/bash

# Estoy usando Python 3.6.7
# Estoy usando kyvy 1.10.1
# Estoy usando Cython 0.28.6

sudo aptitude purge python3-kivy python3-sdl2 python-pip python3-pip
#pip install --upgrade pip --user
# sudo pip3 uninstall cython kivy --user
sudo aptitude reinstall python python3
sudo apt autoremove

sudo aptitude install python3-pip

sudo add-apt-repository ppa:kivy-team/kivy
sudo apt-get update
sudo apt-get install python3-kivy