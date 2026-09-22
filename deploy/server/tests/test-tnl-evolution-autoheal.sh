#!/usr/bin/env bash
# Pruebas de tnl-evolution-autoheal con docker, curl y sleep falsos y reloj simulado.
# No toca Docker ni la API real. Correr como usuario sin acceso a Docker, por ejemplo:
#   runuser -u nobody -- bash test-tnl-evolution-autoheal.sh ../tnl-evolution-autoheal
# Las condiciones de check van entre comillas simples a propósito: las evalúa eval.
# shellcheck disable=SC2016,SC2034
set -u
SCRIPT="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
T0=1790000000                         # reloj simulado (minuto 0)
PASADO="2026-01-01T00:00:00.000000000Z"
PASS=0
FAIL=0

mkdir -p "$T/bin"
cat > "$T/bin/docker" <<'EOF'
#!/usr/bin/env bash
echo "docker $*" >> "$FAKE/calls"
case "$1" in
    inspect) [ "$(cat "$FAKE/inspect_rc")" = 0 ] || exit 1; cat "$FAKE/inspect" ;;
    restart) echo "$*" >> "$FAKE/restarts"; exit "$(cat "$FAKE/restart_rc")" ;;
    *) exit 99 ;;
esac
EOF
# Una respuesta por línea; la última se repite.
cat > "$T/bin/curl" <<'EOF'
#!/usr/bin/env bash
echo "curl $*" >> "$FAKE/calls"
modo="$(head -n 1 "$FAKE/curl")"
if [ "$(wc -l < "$FAKE/curl")" -gt 1 ]; then sed -i '1d' "$FAKE/curl"; fi
case "$modo" in
    ok) printf '{"status":200,"message":"Welcome to the Evolution API, it is working!","version":"2.3.7"}\n200' ;;
    http500) printf '{"status":500,"error":"Internal Server Error"}\n500' ;;
    otro200) printf '<html>otro servicio</html>\n200' ;;
    down) exit 7 ;;
    timeout) exit 28 ;;
esac
EOF
printf '#!/usr/bin/env bash\nexit 0\n' > "$T/bin/sleep"
chmod +x "$T/bin/docker" "$T/bin/curl" "$T/bin/sleep"

reset() {
    rm -rf "$T/fake" "$T/state"
    mkdir -p "$T/fake" "$T/state"
    FAKE="$T/fake"
    : > "$FAKE/calls"
    : > "$FAKE/restarts"
    echo 0 > "$FAKE/inspect_rc"
    echo 0 > "$FAKE/restart_rc"
    contenedor running "$PASADO"
    curl_seq "${1:-ok}"
}
contenedor() { echo "$1 $2 0 none" > "$FAKE/inspect"; }
curl_seq() { printf '%s\n' "$@" > "$FAKE/curl"; }

# run <minuto>: ejecuta el script con el reloj en T0 + minuto*60.
run() {
    OUT="$(env -i PATH="$T/bin:/usr/bin:/bin" FAKE="$FAKE" DOCKER_HOST="unix:///nonexistent.sock" \
        TNL_AUTOHEAL_STATE_DIR="$T/state" TNL_AUTOHEAL_NOW=$((T0 + $1 * 60)) bash "$SCRIPT" 2>&1)"
    RC=$?
    LAST="$(printf '%s\n' "$OUT" | tail -n 1)"
}
reinicios() { wc -l < "$FAKE/restarts" | tr -d ' '; }

ok()   { PASS=$((PASS + 1)); echo "ok    $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL  $1"; printf '      %s\n' "$OUT" | tail -n 4; }
check() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

# A. sano: sin reinicio, solo lectura en Docker
reset ok; run 0
check "A sano -> sin reinicio" '[ "$RC" = 0 ] && [ "$(reinicios)" = 0 ] && [[ "$LAST" == "health=healthy consecutive_failures=0 "* ]] && [[ "$LAST" == *"action=none restart=0 errors=0" ]]'
check "A Docker solo se consulta (inspect)" '! grep -qvE "^(docker inspect|curl )" "$FAKE/calls"'

# B, C, D. umbral de 3 fallos seguidos
reset down; run 0
check "B 1 fallo -> sin reinicio" '[ "$(reinicios)" = 0 ] && [[ "$LAST" == *"consecutive_failures=1 "*"action=observing restart=0"* ]]'
run 1
check "C 2 fallos -> sin reinicio" '[ "$(reinicios)" = 0 ] && [[ "$LAST" == *"consecutive_failures=2 "* ]]'
run 2
check "D 3er fallo -> un reinicio" '[ "$(reinicios)" = 1 ] && [[ "$LAST" == *"restart=1"* ]]'
check "D usa docker restart del contenedor exacto" 'grep -qx -- "restart -t 20 tnl-evolution" "$FAKE/restarts"'

# E. recuperación verificada tras reiniciar
reset down; curl_seq down down down down ok
run 0; run 1; run 2
check "E recupera tras reiniciar" '[ "$RC" = 0 ] && [ "$(reinicios)" = 1 ] && [[ "$LAST" == "health=healthy consecutive_failures=0 "*"action=restarted restart=1 errors=0" ]]'
run 3
check "E siguiente pasada sana" '[[ "$LAST" == "health=healthy "*"action=none restart=0 errors=0" ]]'

# F. docker restart falla: error controlado y sin bucle
reset down; echo 1 > "$FAKE/restart_rc"
run 0; run 1; run 2
check "F restart falla -> error controlado" '[ "$RC" = 1 ] && [[ "$LAST" == *"action=restart_failed restart=1 errors=1" ]]'
for m in 3 4 5 6 7 8 9 10; do run "$m"; done
check "F sin reintentos inmediatos" '[ "$(reinicios)" = 1 ] && [[ "$LAST" == *"action=cooldown"* ]]'

# G. enfriamiento de 15 min (la API sigue caída tras reiniciar)
reset down
run 0; run 1; run 2
check "G reinicio sin recuperación queda registrado" '[ "$RC" = 1 ] && [[ "$LAST" == *"action=restart_not_recovered restart=1 errors=1" ]]'
for m in $(seq 3 16); do run "$m"; done
check "G enfriamiento bloquea hasta el minuto 16" '[ "$(reinicios)" = 1 ] && [[ "$LAST" == *"action=cooldown"* ]]'
run 17
check "G a los 15 min se permite otro" '[ "$(reinicios)" = 2 ]'

# H. máximo 3 reinicios por hora móvil
reset down
for m in $(seq 0 47); do run "$m"; done
check "H 4o reinicio bloqueado en la hora" '[ "$(reinicios)" = 3 ] && [ "$RC" = 1 ] && [[ "$LAST" == *"action=hourly_limit"* ]] && [[ "$OUT" == *"requiere atención manual"* ]]'
for m in $(seq 48 61); do run "$m"; done
check "H sigue bloqueado dentro de la hora" '[ "$(reinicios)" = 3 ]'
run 62
check "H al salir el 1o de la ventana se permite" '[ "$(reinicios)" = 4 ]'

# I. una revisión sana reinicia el contador
reset down; curl_seq down down ok down down down
run 0; run 1; run 2; run 3; run 4
check "I sano reinicia el contador" '[ "$(reinicios)" = 0 ] && [[ "$LAST" == *"consecutive_failures=2 "* ]]'
run 5
check "I tres fallos nuevos -> reinicio" '[ "$(reinicios)" = 1 ]'

# J. estado corrupto: falla de forma segura
reset down
printf 'esto no es un estado\nconsecutive_failures=99\n' > "$T/state/state"
run 0
check "J corrupto -> sin acción y error visible" '[ "$RC" = 1 ] && [ "$(reinicios)" = 0 ] && [[ "$OUT" == *"estado ilegible o inválido"* ]]'
check "J estado reescrito válido" 'grep -qx "version=1" "$T/state/state" && grep -qx "last_restart=$T0" "$T/state/state"'
for m in $(seq 1 14); do run "$m"; done
check "J sin reinicio durante 15 min" '[ "$(reinicios)" = 0 ]'
run 15
check "J después, flujo normal" '[ "$(reinicios)" = 1 ]'
for contenido in "" "version=2" "version=1
restarts=abc" "version=1
consecutive_failures=08"; do
    reset down; printf '%s' "$contenido" > "$T/state/state"; run 0
    check "J variante corrupta rechazada" '[ "$RC" = 1 ] && [[ "$OUT" == *"estado ilegible"* ]] && [ "$(reinicios)" = 0 ]'
done

# K. candado: dos ejecuciones no se cruzan
reset down
exec 8>"$T/state/lock"
flock 8
run 0
exec 8>&-
check "K ejecución concurrente se salta" '[ "$RC" = 0 ] && [ "$LAST" = "health=skipped action=busy restart=0 errors=0" ] && [ ! -s "$FAKE/calls" ]'

# L. el estado no guarda datos sensibles
reset down; run 0; run 1; run 2; run 3
check "L solo claves permitidas" '! grep -qvE "^(version=1|consecutive_failures=[0-9]+|last_status=[a-z_]+|last_check=[0-9]+|last_restart=[0-9]+|restarts=([0-9]+( [0-9]+)*)?)$" "$T/state/state"'
check "L permisos 0600" '[ "$(stat -c %a "$T/state/state")" = 600 ]'
check "L sin temporales" '[ "$(ls -A "$T/state" | sort | tr "\n" " ")" = "lock state " ]'

# M. una sesión WhatsApp caída no reinicia el contenedor
reset ok
for m in $(seq 0 5); do run "$m"; done
check "M solo consulta GET / (nunca /instance/)" '! grep -q "/instance/" "$FAKE/calls" && [ "$(grep -c "^curl .* http://127.0.0.1:8082/$" "$FAKE/calls")" = 6 ]'
check "M sin reinicio con la API sana" '[ "$(reinicios)" = 0 ]'
check "M el script no usa otros comandos de Docker" '[ "$(grep -v "^[[:space:]]*#" "$SCRIPT" | grep -oE "docker (compose|rm|stop|kill|run|pull|up|down|exec|update|restart|inspect)" | sort -u | tr "\n" " ")" = "docker inspect docker restart " ]'

# N. timeout y respuestas inválidas cuentan como fallo
for modo in timeout http500 otro200; do
    reset "$modo"; run 0; run 1; run 2
    check "N $modo cuenta como fallo" '[ "$(reinicios)" = 1 ]'
done

# O. Docker no responde: sin reinicio y sin bucle
reset down; echo 1 > "$FAKE/inspect_rc"
for m in $(seq 0 10); do run "$m"; done
check "O docker falla -> sin reinicio" '[ "$(reinicios)" = 0 ] && [ "$RC" = 1 ] && [[ "$LAST" == "health=docker_error "*"restart=0 errors=1" ]]'

# Extra: contenedor detenido a mano o reiniciándose: no se toca
for estado in exited paused restarting; do
    reset down; contenedor "$estado" "$PASADO"
    for m in $(seq 0 5); do run "$m"; done
    check "X $estado -> no se toca" '[ "$(reinicios)" = 0 ] && [[ "$LAST" == "health=not_running "* ]]'
done

# Extra: recién arrancado, los fallos no cuentan
reset down; contenedor running "$(date -u -d @$((T0 - 60)) +%FT%TZ)"
run 0; run 1
check "X arranque reciente -> starting" '[ "$(reinicios)" = 0 ] && [[ "$LAST" == "health=starting consecutive_failures=0 "* ]]'

# Extra: si no se puede guardar el intento, no se reinicia
if [ "$(id -u)" = 0 ]; then
    echo "skip  X estado no guardable (root ignora permisos)"
else
    reset down; run 0; run 1; chmod 500 "$T/state"
    run 2
    chmod 700 "$T/state"
    check "X intento no guardado -> sin reinicio" '[ "$(reinicios)" = 0 ] && [[ "$LAST" == *"action=state_not_saved restart=0 errors=1" ]]'
fi

echo "passed=$PASS failed=$FAIL"
[ "$FAIL" = 0 ]
