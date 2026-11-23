QT += core gui qml quick quickcontrols2 dbus

CONFIG += c++17 release
TARGET = daobuds
TEMPLATE = app

HEADERS += \
    src/gaia.h \
    src/backend.h \
    src/theme.h \
    src/translator.h

SOURCES += \
    src/main.cpp \
    src/gaia.cpp \
    src/backend.cpp \
    src/theme.cpp \
    src/translator.cpp

RESOURCES += src/resources.qrc
