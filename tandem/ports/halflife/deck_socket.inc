
// ------------------------------------------------------------------ Tandem (Linux handheld)
// Appended by tandem/ports/halflife/build.sh: there the deck is Tandem's bottom screen, and a local socket takes the
// place of the Android JNI bridge. It starts when the client library is loaded.
#include "tandem_deck.h"

static struct TandemDeckBoot
{
	TandemDeckBoot() { TandemDeck_Start( ThorHUD_Snapshot, ThorHUD_Command ); }
} tandemDeckBoot;
