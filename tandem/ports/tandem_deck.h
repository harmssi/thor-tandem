/*
 * tandem_deck.h - the game's end of a Tandem deck socket (protocol: tandem/README.md, "Deck-Socket").
 *
 * Header only: include it in one source file of a port and call TandemDeck_Start() once. Without TANDEM_DECK_SOCKET in
 * the environment (the game was not started by Tandem) nothing happens. The game listens on that Unix socket; the deck
 * on the bottom screen connects, gets the state as JSON lines (and binary blocks, see TandemDeck_Block) and sends
 * commands as text lines.
 */
#ifndef TANDEM_DECK_H
#define TANDEM_DECK_H

#include <errno.h>
#include <poll.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

/* Writes the state as one JSON object without line breaks, NUL-terminated; returns its length, 0 if there is none yet. */
typedef int (*tandem_deck_state_fn)( char *buf, int size );
/* One command line from the deck. Runs on the socket's thread: check it and queue it for the game's own thread. */
typedef void (*tandem_deck_command_fn)( const char *line );

static tandem_deck_state_fn tandem_deck_state;
static tandem_deck_command_fn tandem_deck_command;
static int tandem_deck_listener = -1;
static int tandem_deck_fd = -1; /* the deck's connection, while the socket's thread is inside a callback */

static int tandem_deck_send( int fd, const char *data, size_t size )
{
	while( size > 0 )
	{
		ssize_t n = send( fd, data, size, MSG_NOSIGNAL );
		if( n <= 0 )
			return 0;
		data += n;
		size -= (size_t)n;
	}
	return 1;
}

/*
 * A binary block for the deck (a radar picture, an icon): the line "#<name> <size>\n", then size raw bytes. The name has
 * no spaces; what the bytes mean is the game's and its deck's business. Only from inside the state or the command
 * callback: they run on the socket's thread, between two lines. Returns 0 when the deck is gone.
 */
__attribute__((unused)) static int TandemDeck_Block( const char *name, const void *data, size_t size )
{
	char head[96];
	int n = snprintf( head, sizeof( head ), "#%.64s %zu\n", name, size );
	return tandem_deck_fd >= 0 && tandem_deck_send( tandem_deck_fd, head, (size_t)n )
		&& tandem_deck_send( tandem_deck_fd, (const char *)data, size );
}

static void *tandem_deck_thread( void *unused )
{
	static char now[32768], sent[32768], in[512];
	const char *hello = getenv( "TANDEM_DECK_HELLO" ); /* one JSON line of the launcher's own, sent first */
	(void)unused;

	for( ;; )
	{
		int fd = accept( tandem_deck_listener, NULL, NULL ), ok = 1;
		size_t used = 0;
		if( fd < 0 )
		{
			if( errno == EINTR )
				continue;
			return NULL;
		}
		sent[0] = 0;
		tandem_deck_fd = fd;
		if( hello && hello[0] )
			ok = tandem_deck_send( fd, hello, strlen( hello )) && tandem_deck_send( fd, "\n", 1 );
		while( ok )
		{
			struct pollfd p = { fd, POLLIN, 0 };
			int n;
			if( poll( &p, 1, 50 ) > 0 ) /* 50 ms: the state goes out twenty times a second at most */
			{
				char *line = in, *end;
				ssize_t got = recv( fd, in + used, sizeof( in ) - 1 - used, 0 );
				if( got <= 0 )
					break;
				used += (size_t)got;
				in[used] = 0;
				while(( end = strchr( line, '\n' )) != NULL )
				{
					*end = 0;
					if( end > line && end[-1] == '\r' )
						end[-1] = 0;
					tandem_deck_command( line );
					line = end + 1;
				}
				used = (size_t)( in + used - line );
				memmove( in, line, used );
				if( used == sizeof( in ) - 1 )
					used = 0; /* longer than any command: dropped */
			}
			n = tandem_deck_state( now, (int)sizeof( now ) - 1 );
			if( n > 0 && strcmp( now, sent ))
			{
				memcpy( sent, now, (size_t)n + 1 );
				now[n] = '\n';
				ok = tandem_deck_send( fd, now, (size_t)n + 1 );
			}
		}
		tandem_deck_fd = -1;
		close( fd );
	}
}

static void TandemDeck_Start( tandem_deck_state_fn state, tandem_deck_command_fn command )
{
	const char *path = getenv( "TANDEM_DECK_SOCKET" );
	struct sockaddr_un addr;
	pthread_t thread;
	int fd;

	if( !path || !path[0] || strlen( path ) >= sizeof( addr.sun_path ) || tandem_deck_listener >= 0 )
		return;
	fd = socket( AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0 );
	if( fd < 0 )
		return;
	memset( &addr, 0, sizeof( addr ));
	addr.sun_family = AF_UNIX;
	strcpy( addr.sun_path, path );
	unlink( path ); /* left behind by a game that did not end cleanly */
	if( bind( fd, (struct sockaddr *)&addr, sizeof( addr )) || listen( fd, 1 ))
	{
		tandem_deck_fd = -1;
		close( fd );
		return;
	}
	tandem_deck_listener = fd;
	tandem_deck_state = state;
	tandem_deck_command = command;
	if( !pthread_create( &thread, NULL, tandem_deck_thread, NULL ))
		pthread_detach( thread );
}

#endif
