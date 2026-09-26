#!/bin/sh
# Reapplies gitignored secondary Redis ACL users after every container start.
# Started as the image entrypoint; then runs the original docker-entrypoint.sh
# with the same redis-server / --requirepass flags Compose already passes.
# Does not touch the default user and does not use --aclfile.
set -eu

ORIGINAL_ENTRYPOINT="/usr/local/bin/docker-entrypoint.sh"
ACL_DIR="${ACL_RESTORE_DIR:-/acl-restore}"
REDIS_PID=""

log() {
	echo "redis-acl-restore: $*" >&2
}

term_handler() {
	if [ -n "$REDIS_PID" ]; then
		kill -TERM "$REDIS_PID" 2>/dev/null || true
		wait "$REDIS_PID" || true
	fi
	exit 0
}
trap term_handler TERM INT

if [ -z "${REDIS_PASSWORD:-}" ]; then
	log "REDIS_PASSWORD is empty; refusing to start"
	exit 1
fi

if [ "$#" -eq 0 ]; then
	set -- redis-server --appendonly yes --appendfsync everysec --requirepass "$REDIS_PASSWORD" --maxmemory-policy noeviction
fi

"$ORIGINAL_ENTRYPOINT" "$@" &
REDIS_PID=$!

i=0
ready=0
while [ "$i" -lt 200 ]; do
	if redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ping 2>/dev/null | grep -q PONG; then
		ready=1
		break
	fi
	i=$((i + 1))
	sleep 0.1
done

if [ "$ready" -ne 1 ]; then
	log "Redis did not become ready; not applying secondary ACLs"
	wait "$REDIS_PID"
	exit $?
fi

restore_count=0
restore_one() {
	_f=$1
	[ -f "$_f" ] || return 0
	_url=$(grep '^FARM_BROKER_URL=' "$_f" | head -n 1 | cut -d= -f2- | tr -d '\r')
	[ -n "$_url" ] || {
		log "no FARM_BROKER_URL in $(basename "$_f"); skipping"
		return 0
	}
	_rest=${_url#redis://}
	_userpass=${_rest%%@*}
	_user=${_userpass%%:*}
	_pass=${_userpass#*:}
	if [ -z "$_user" ] || [ "$_user" = "default" ]; then
		log "skipping default/empty user in $(basename "$_f")"
		return 0
	fi
	case "$_user" in
	*[!A-Za-z0-9_-]*)
		log "skipping unsafe username in $(basename "$_f")"
		return 0
		;;
	esac
	if [ -z "$_pass" ] || [ "$_pass" = "$_userpass" ]; then
		log "missing password for '$_user'; skipping"
		return 0
	fi
	if redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ACL SETUSER "$_user" on ">$_pass" '~*' '&*' nocommands '+@all' -flushall -flushdb -config -shutdown -acl -debug -cluster -replicaof | grep -q OK; then
		log "restored ACL user '$_user'"
		restore_count=$((restore_count + 1))
	else
		log "ACL SETUSER failed for '$_user'"
	fi
}

if [ -d "$ACL_DIR" ]; then
	# Literal unmatched globs are ignored by the [ -f ] check inside restore_one.
	for f in "$ACL_DIR"/.env.*.generated; do
		restore_one "$f"
	done
else
	log "ACL restore directory '$ACL_DIR' is missing"
fi
log "restored $restore_count secondary ACL user(s)"

wait "$REDIS_PID"
