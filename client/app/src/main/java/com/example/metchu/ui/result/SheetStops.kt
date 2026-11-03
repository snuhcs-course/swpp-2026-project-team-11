package com.example.metchu.ui.result

/** Where the result sheet rests, top to bottom: almost full, half, and folded to one row. */
enum class SheetStop { FULL, HALF, PEEK }

/** A tap on the sheet's header: up one stop, or back to half from the top. */
fun tappedStop(from: SheetStop): SheetStop = when (from) {
    SheetStop.PEEK -> SheetStop.HALF
    SheetStop.HALF -> SheetStop.FULL
    SheetStop.FULL -> SheetStop.HALF
}

/**
 * Where a drag settles: the stop nearest the sheet, or one stop on in the drag's direction
 * ([down] or up) once the finger has gone [far] enough but the sheet is still nearest [from].
 */
fun draggedStop(from: SheetStop, nearest: SheetStop, down: Boolean, far: Boolean): SheetStop {
    if (nearest != from || !far) return nearest
    return SheetStop.entries.getOrElse(from.ordinal + if (down) 1 else -1) { from }
}
