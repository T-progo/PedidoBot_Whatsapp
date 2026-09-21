/* NEGOCIOLISTO-THEME-V2 */

(function () {

    "use strict";

    const STORAGE_KEY =
        "negociolisto-theme";


    function getTheme() {

        const current =
            document.documentElement
                .getAttribute("data-theme");

        return current === "light"
            ? "light"
            : "dark";

    }


    function setTheme(theme) {

        const normalized =
            theme === "light"
                ? "light"
                : "dark";

        document.documentElement
            .setAttribute(
                "data-theme",
                normalized
            );

        try {

            localStorage.setItem(
                STORAGE_KEY,
                normalized
            );

        } catch (error) {

            // El tema sigue funcionando
            // aunque localStorage esté bloqueado.

        }


        document
            .querySelectorAll(
                "[data-theme-toggle]"
            )
            .forEach(function (button) {

                const dark =
                    normalized === "dark";

                button.innerHTML =
                    dark
                        ? "<span aria-hidden=\"true\">☀️</span><span>Claro</span>"
                        : "<span aria-hidden=\"true\">🌙</span><span>Oscuro</span>";

                button.setAttribute(
                    "aria-label",
                    dark
                        ? "Cambiar a tema claro"
                        : "Cambiar a tema oscuro"
                );

                button.setAttribute(
                    "title",
                    dark
                        ? "Cambiar a tema claro"
                        : "Cambiar a tema oscuro"
                );

            });

    }


    function toggleTheme() {

        setTheme(
            getTheme() === "dark"
                ? "light"
                : "dark"
        );

    }


    function init() {

        setTheme(
            getTheme()
        );


        document
            .querySelectorAll(
                "[data-theme-toggle]"
            )
            .forEach(function (button) {

                button.addEventListener(
                    "click",
                    toggleTheme
                );

            });

    }


    if (
        document.readyState === "loading"
    ) {

        document.addEventListener(
            "DOMContentLoaded",
            init
        );

    } else {

        init();

    }


    window.addEventListener(
        "storage",
        function (event) {

            if (
                event.key === STORAGE_KEY
                &&
                (
                    event.newValue === "light"
                    ||
                    event.newValue === "dark"
                )
            ) {

                setTheme(
                    event.newValue
                );

            }

        }
    );

})();
