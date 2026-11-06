#!/bin/sh
# Reapplies gitignored secondary Redis ACL users after every container start.
# Started as the image entrypoint; then runs the original docker-entrypoint.sh
# with the redis-server flags Compose passes, plus a private config file that
# carries `requirepass` so the password is never on the redis-server command
# line (`ps` inside the container, `docker inspect`, compose logs).
# redis-cli authenticates through REDISCLI_AUTH (never `-a`), and ACL SETUSER
# lines are fed on stdin so secondary passwords are not on argv either.
# Does not touch the default user and does not use --aclfile.
set -eu

ORIGINAL_ENTRYPOINT="/usr/local/bin/docker-entrypoint.sh"
ACL_DIR="${ACL_RESTORE_DIR:-/acl-restore}"
REQUIREPASS_CONF="${REDIS_REQUIREPASS_CONF:-/tmp/redis-requirepass.conf}"
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

# redis-cli reads its password from the environment, so no `-a` anywhere.
REDISCLI_AUTH="$REDIS_PASSWORD"
export REDISCLI_AUTH

# requirepass lives in a 0600 config file handed to redis-server as its first
# argument; later flags still override. umask keeps the file private from the
# moment it is created, then it is chowned to the redis user the image drops
# to (docker-entrypoint.sh uses gosu when started as root).
_saved_umask=$(umask)
umask 077
printf 'requirepass %s\n' "$REDIS_PASSWORD" > "$REQUIREPASS_CONF"
chmod 600 "$REQUIREPASS_CONF"
chown redis:redis "$REQUIREPASS_CONF" 2>/dev/null || true
umask "$_saved_umask"

if [ "$#" -eq 0 ]; then
	set -- redis-server --appendonly yes --appendfsync everysec --maxmemory-policy noeviction
fi
if [ "$1" = "redis-server" ]; then
	shift
	set -- redis-server "$REQUIREPASS_CONF" "$@"
fi

"$ORIGINAL_ENTRYPOINT" "$@" &
REDIS_PID=$!

i=0
ready=0
while [ "$i" -lt 200 ]; do
	if redis-cli --no-auth-warning ping 2>/dev/null | grep -q PONG; then
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
	# Same grant set as Add-/Restore-Phase1SecondaryWorkerCredential*.ps1:
	# explicit categories instead of +@all; @dangerous, replication, module,
	# KEYS and SELECT denied (the user stays on the db 0 named in its URL).
	# The line is piped on stdin so the password never reaches argv.
	_acl="ACL SETUSER $_user on >$_pass ~* &* nocommands"
	_acl="$_acl +@read +@write +@list +@hash +@string +@set +@sortedset +@stream +@pubsub +@scripting +@transaction +@connection"
	_acl="$_acl -@dangerous -slaveof -replicaof -module -keys -select -flushall -flushdb -config -shutdown -acl -debug -cluster"
	if printf '%s\n' "$_acl" | redis-cli --no-auth-warning | grep -q OK; then
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
