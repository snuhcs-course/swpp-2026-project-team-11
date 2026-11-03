package com.example.metchu.ui.result

/** Where the result sheet rests, top to bottom: almost full, half, and folded to one row. */
enum class SheetStop { FULL, HALF, PEEK }

/** The stops a dish offers: one cafeteria fits at half height, so it has no full stop. */
fun sheetStops(cafeterias: Int): List<SheetStop> =
    if (cafeterias > 1) SheetStop.entries else listOf(SheetStop.HALF, SheetStop.PEEK)

/** A tap on the handle: up one stop, or back to half from the highest one there is. */
fun tappedStop(stops: List<SheetStop>, from: SheetStop): SheetStop = when (from) {
    SheetStop.PEEK -> SheetStop.HALF
    SheetStop.HALF -> if (SheetStop.FULL in stops) SheetStop.FULL else SheetStop.PEEK
    SheetStop.FULL -> SheetStop.HALF
}

/**
 * Where a drag settles: the stop nearest the sheet, or one stop on in the drag's direction
 * ([down] or up) once the finger has gone [far] enough but the sheet is still nearest [from].
 */
fun draggedStop(stops: List<SheetStop>, from: SheetStop, nearest: SheetStop, down: Boolean, far: Boolean): SheetStop {
    if (nearest != from || !far) return nearest
    val index = stops.indexOf(from) + if (down) 1 else -1
    return stops.getOrElse(index) { from }
}
