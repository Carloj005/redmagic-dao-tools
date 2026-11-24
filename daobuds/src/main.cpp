// daobuds — Native Omarchy desktop controller for Redmagic Cyberbuds DAO TWS (BH4010).

#include <QCoreApplication>
#include <QGuiApplication>
#include <QIcon>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickStyle>
#include <QUrl>
#include <iostream>

#include "backend.h"
#include "gaia.h"
#include "theme.h"
#include "translator.h"

int main(int argc, char *argv[]) {
    // Support headless status JSON query so shell plugins and scripts can reuse one binary.
    if (argc >= 2 && QString::fromLocal8Bit(argv[1]) == "status") {
        qputenv("QT_QPA_PLATFORM", "offscreen");
        QCoreApplication cliApp(argc, argv);
        QString macOverride;
        for (int i = 2; i + 1 < argc; ++i) {
            if (QString::fromLocal8Bit(argv[i]) == "--mac")
                macOverride = QString::fromLocal8Bit(argv[i + 1]);
        }
        const DaoStatus st = Gaia::queryFullStatus(macOverride);
        std::cout << Backend::statusToJson(st).constData() << "\n";
        return (st.btConnected || st.dongleConnected) ? 0 : 1;
    }

    QGuiApplication app(argc, argv);
    app.setApplicationName("daobuds");
    app.setApplicationVersion("1.0.0");
    app.setDesktopFileName("daobuds");
    app.setWindowIcon(QIcon::fromTheme("daobuds"));

    QQuickStyle::setStyle("Material");

    Translator translator;
    app.installTranslator(&translator);

    Theme theme;
    Backend backend;

    QQmlApplicationEngine engine;
    QObject::connect(&translator, &Translator::changed, &engine, &QQmlEngine::retranslate);
    engine.rootContext()->setContextProperty("translator", &translator);
    engine.rootContext()->setContextProperty("theme", &theme);
    engine.rootContext()->setContextProperty("backend", &backend);
    engine.load(QUrl("qrc:/Main.qml"));
    if (engine.rootObjects().isEmpty())
        return 1;

    return app.exec();
}
