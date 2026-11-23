QT += core gui quick quickcontrols2 testlib dbus
CONFIG += c++17 testcase
TARGET = daobuds_tests
TEMPLATE = app

INCLUDEPATH += ../src

HEADERS += ../src/gaia.h ../src/backend.h ../src/theme.h ../src/translator.h
SOURCES += daobuds_tests.cpp ../src/gaia.cpp ../src/backend.cpp ../src/theme.cpp ../src/translator.cpp
