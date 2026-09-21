#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

FULL_ROOT="/opt/tunegociolisto/backups/full"

KEEP="${KEEP:-7}"
DRY_RUN="${DRY_RUN:-1}"

echo "=============================================="
echo " NEGOCIOLISTO - ROTACION DE BACKUPS"
echo "=============================================="
echo "Fecha      : $(date -Is)"
echo "Retencion : $KEEP backups automaticos"
echo "Dry Run    : $DRY_RUN"
echo

if [ ! -d "$FULL_ROOT" ]; then
    echo "ERROR: no existe $FULL_ROOT"
    exit 1
fi

CANDIDATES=()

while IFS= read -r NAME; do

    DIR="$FULL_ROOT/$NAME"

    # Nunca eliminar Golden Backup
    if [ -f "$DIR/.golden" ]; then
        echo "PROTEGIDO : $NAME [GOLDEN]"
        continue
    fi

    # Solo rotar backups correctamente validados
    if [ ! -f "$DIR/metadata/VALIDATED" ]; then
        echo "IGNORADO  : $NAME [NO VALIDATED]"
        continue
    fi

    # Nunca considerar un backup fallido como válido
    if [ -e "$DIR/FAILED" ]; then
        echo "IGNORADO  : $NAME [FAILED]"
        continue
    fi

    CANDIDATES+=("$NAME")

done < <(
    find "$FULL_ROOT" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    -printf '%f\n' \
    | sort
)

COUNT="${#CANDIDATES[@]}"

echo
echo "Backups automaticos VALIDATED encontrados: $COUNT"

if [ "$COUNT" -le "$KEEP" ]; then
    echo "OK: no se requiere rotacion"
    exit 0
fi

REMOVE_COUNT=$((COUNT - KEEP))

echo "Backups a retirar: $REMOVE_COUNT"
echo

for ((I=0; I<REMOVE_COUNT; I++)); do

    NAME="${CANDIDATES[$I]}"
    DIR="$FULL_ROOT/$NAME"
    SEAL="$FULL_ROOT/$NAME.SHA256"

    if [ "$DRY_RUN" = "1" ]; then

        echo "DRY-RUN eliminaria:"
        echo "  $DIR"

        if [ -f "$SEAL" ]; then
            echo "  $SEAL"
        fi

    else

        echo "ELIMINANDO: $NAME"

        rm -rf -- "$DIR"
        rm -f -- "$SEAL"

        echo "OK: eliminado $NAME"

    fi

done

echo
echo "=============================================="
echo " ROTACION COMPLETADA"
echo "=============================================="
