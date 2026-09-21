/* NEGOCIOLISTO-UI-FINAL-V1 */

(function () {

    "use strict";

    var ADMIN_KEY =
        "negociolisto-admin-sidebar-collapsed";

    var CLIENT_KEY =
        "negociolisto-client-sidebar-collapsed";


    function safeGet(key) {

        try {
            return localStorage.getItem(key);
        } catch (error) {
            return null;
        }
    }


    function safeSet(key, value) {

        try {
            localStorage.setItem(
                key,
                value
            );
        } catch (error) {
            /* UI sigue funcionando sin storage. */
        }
    }


    function normalize(text) {

        return (
            text
                .replace(/\s+/g, " ")
                .trim()
                .toLowerCase()
        );
    }


    function getShortLabel(text) {

        var value = normalize(text);

        var labels = {
            "inicio": "IN",
            "clientes": "CL",
            "usuarios": "US",
            "licencias": "LI",
            "bots": "BO",
            "canales": "CA",
            "plantillas maestras": "PM",
            "plantillas clientes": "PC",
            "variables": "VA",
            "catálogos": "CT",
            "catalogos": "CT",
            "productos": "PR",
            "pedidos": "PE",

            "mi negocio": "MN",
            "licencia": "LI",
            "automatización": "AU",
            "automatizacion": "AU",
            "whatsapp": "WA",
            "catálogo": "CT",
            "catalogo": "CT"
        };

        if (labels[value]) {
            return labels[value];
        }

        var words =
            value
                .split(" ")
                .filter(Boolean);

        if (!words.length) {
            return "•";
        }

        if (words.length === 1) {
            return words[0]
                .slice(0, 2)
                .toUpperCase();
        }

        return (
            words[0][0]
            + words[1][0]
        ).toUpperCase();
    }


    function prepareLinks(selector) {

        document
            .querySelectorAll(selector)
            .forEach(function (link) {

                var label =
                    link.textContent
                        .replace(/\s+/g, " ")
                        .trim();

                if (!label) {
                    return;
                }

                link.setAttribute(
                    "data-short",
                    getShortLabel(label)
                );

                if (
                    !link.hasAttribute("title")
                ) {
                    link.setAttribute(
                        "title",
                        label
                    );
                }
            });
    }


    function closeAdminMobile() {

        document.body.classList.remove(
            "nl-mobile-nav-open"
        );

        var button =
            document.querySelector(
                "[data-mobile-nav-toggle]"
            );

        if (button) {
            button.setAttribute(
                "aria-expanded",
                "false"
            );
        }
    }


    function initAdmin() {

        var sidebar =
            document.querySelector(
                ".sidebar"
            );

        if (!sidebar) {
            return;
        }

        prepareLinks(
            ".sidebar .menu-item"
        );


        var collapse =
            document.querySelector(
                "[data-sidebar-collapse]"
            );

        var mobile =
            document.querySelector(
                "[data-mobile-nav-toggle]"
            );

        var overlay =
            document.querySelector(
                "[data-sidebar-overlay]"
            );


        if (
            safeGet(ADMIN_KEY)
            === "1"
        ) {
            document.body.classList.add(
                "nl-sidebar-collapsed"
            );
        }


        if (collapse) {

            collapse.addEventListener(
                "click",
                function () {

                    if (
                        window.innerWidth
                        <= 1100
                    ) {
                        return;
                    }

                    document.body
                        .classList
                        .toggle(
                            "nl-sidebar-collapsed"
                        );

                    var collapsed =
                        document.body
                            .classList
                            .contains(
                                "nl-sidebar-collapsed"
                            );

                    safeSet(
                        ADMIN_KEY,
                        collapsed
                            ? "1"
                            : "0"
                    );

                    collapse.setAttribute(
                        "aria-label",
                        collapsed
                            ? "Expandir menú"
                            : "Minimizar menú"
                    );

                    collapse.setAttribute(
                        "title",
                        collapsed
                            ? "Expandir menú"
                            : "Minimizar menú"
                    );
                }
            );
        }


        if (mobile) {

            mobile.addEventListener(
                "click",
                function () {

                    var open =
                        document.body
                            .classList
                            .toggle(
                                "nl-mobile-nav-open"
                            );

                    mobile.setAttribute(
                        "aria-expanded",
                        open
                            ? "true"
                            : "false"
                    );
                }
            );
        }


        if (overlay) {

            overlay.addEventListener(
                "click",
                closeAdminMobile
            );
        }


        sidebar
            .querySelectorAll("a")
            .forEach(function (link) {

                link.addEventListener(
                    "click",
                    function () {

                        if (
                            window.innerWidth
                            <= 800
                        ) {
                            closeAdminMobile();
                        }
                    }
                );
            });
    }


    function closeClientMobile() {

        document.body.classList.remove(
            "cp-mobile-nav-open"
        );

        var button =
            document.querySelector(
                "[data-cp-mobile-nav-toggle]"
            );

        if (button) {
            button.setAttribute(
                "aria-expanded",
                "false"
            );
        }
    }


    function initClient() {

        var sidebar =
            document.querySelector(
                ".cp-sidebar"
            );

        if (!sidebar) {
            return;
        }


        prepareLinks(
            ".cp-sidebar .cp-nav a"
        );


        var collapse =
            document.querySelector(
                "[data-cp-sidebar-collapse]"
            );

        var mobile =
            document.querySelector(
                "[data-cp-mobile-nav-toggle]"
            );

        var overlay =
            document.querySelector(
                "[data-cp-sidebar-overlay]"
            );


        if (
            safeGet(CLIENT_KEY)
            === "1"
        ) {
            document.body.classList.add(
                "cp-sidebar-collapsed"
            );
        }


        if (collapse) {

            collapse.addEventListener(
                "click",
                function () {

                    if (
                        window.innerWidth
                        <= 1050
                    ) {
                        return;
                    }

                    document.body
                        .classList
                        .toggle(
                            "cp-sidebar-collapsed"
                        );

                    var collapsed =
                        document.body
                            .classList
                            .contains(
                                "cp-sidebar-collapsed"
                            );

                    safeSet(
                        CLIENT_KEY,
                        collapsed
                            ? "1"
                            : "0"
                    );

                    collapse.setAttribute(
                        "aria-label",
                        collapsed
                            ? "Expandir menú"
                            : "Minimizar menú"
                    );

                    collapse.setAttribute(
                        "title",
                        collapsed
                            ? "Expandir menú"
                            : "Minimizar menú"
                    );
                }
            );
        }


        if (mobile) {

            mobile.addEventListener(
                "click",
                function () {

                    var open =
                        document.body
                            .classList
                            .toggle(
                                "cp-mobile-nav-open"
                            );

                    mobile.setAttribute(
                        "aria-expanded",
                        open
                            ? "true"
                            : "false"
                    );
                }
            );
        }


        if (overlay) {

            overlay.addEventListener(
                "click",
                closeClientMobile
            );
        }


        sidebar
            .querySelectorAll(".cp-nav a")
            .forEach(function (link) {

                link.addEventListener(
                    "click",
                    function () {

                        if (
                            window.innerWidth
                            <= 760
                        ) {
                            closeClientMobile();
                        }
                    }
                );
            });
    }


    function initGlobal() {

        document.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key
                    !== "Escape"
                ) {
                    return;
                }

                closeAdminMobile();
                closeClientMobile();
            }
        );


        window.addEventListener(
            "resize",
            function () {

                if (
                    window.innerWidth
                    > 800
                ) {
                    closeAdminMobile();
                }

                if (
                    window.innerWidth
                    > 760
                ) {
                    closeClientMobile();
                }
            }
        );
    }


    function init() {

        initAdmin();
        initClient();
        initGlobal();
    }


    if (
        document.readyState
        === "loading"
    ) {

        document.addEventListener(
            "DOMContentLoaded",
            init
        );

    } else {

        init();
    }

})();


/* ============================================================
   NEGOCIOLISTO-MOBILE-JS-V3
   ============================================================ */

(function () {

    "use strict";


    function enhanceTables() {

        document
            .querySelectorAll(
                ".data-table"
            )
            .forEach(function (table) {

                var headers =
                    Array.from(
                        table.querySelectorAll(
                            "thead th"
                        )
                    )
                    .map(function (th) {

                        return (
                            th.textContent
                                .replace(/\s+/g, " ")
                                .trim()
                        );
                    });


                if (!headers.length) {
                    return;
                }


                table.classList.add(
                    "tnl-mobile-cards"
                );


                table
                    .querySelectorAll(
                        "tbody tr"
                    )
                    .forEach(function (row) {

                        Array.from(
                            row.children
                        )
                        .forEach(
                            function (
                                cell,
                                index
                            ) {

                                if (
                                    cell.tagName
                                    !== "TD"
                                ) {
                                    return;
                                }


                                cell.setAttribute(
                                    "data-mobile-label",
                                    headers[index]
                                    || ""
                                );
                            }
                        );
                    });
            });
    }


    function closeDrawer() {

        document.body
            .classList
            .remove(
                "nl-mobile-nav-open"
            );
    }


    function initMobileMenu() {

        var sidebar =
            document.querySelector(
                ".sidebar"
            );


        if (!sidebar) {
            return;
        }


        var oldButton =
            document.querySelector(
                "[data-mobile-nav-toggle]"
            );


        /*
         * Botón totalmente independiente
         * del layout del topbar.
         */
        var button =
            document.querySelector(
                ".nl-mobile-fab"
            );


        if (!button) {

            button =
                document.createElement(
                    "button"
                );

            button.type =
                "button";

            button.className =
                "nl-mobile-fab";

            button.setAttribute(
                "aria-label",
                "Abrir menú"
            );

            button.setAttribute(
                "title",
                "Menú"
            );

            document.body.appendChild(
                button
            );
        }


        button.addEventListener(
            "click",
            function () {

                var open =
                    document.body
                        .classList
                        .toggle(
                            "nl-mobile-nav-open"
                        );


                button.setAttribute(
                    "aria-label",
                    open
                        ? "Cerrar menú"
                        : "Abrir menú"
                );
            }
        );


        if (oldButton) {
            oldButton.setAttribute(
                "aria-hidden",
                "true"
            );
        }


        var overlay =
            document.querySelector(
                "[data-sidebar-overlay]"
            );


        if (overlay) {

            overlay.addEventListener(
                "click",
                closeDrawer
            );
        }


        sidebar
            .querySelectorAll("a")
            .forEach(function (link) {

                link.addEventListener(
                    "click",
                    function () {

                        if (
                            window.innerWidth
                            <= 800
                        ) {
                            closeDrawer();
                        }
                    }
                );
            });


        document.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key
                    === "Escape"
                ) {
                    closeDrawer();
                }
            }
        );
    }


    function init() {

        enhanceTables();
        initMobileMenu();
    }


    if (
        document.readyState
        === "loading"
    ) {

        document.addEventListener(
            "DOMContentLoaded",
            init
        );

    } else {

        init();
    }

})();

