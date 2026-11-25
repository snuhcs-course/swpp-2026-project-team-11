package com.example.metchu.data

import com.example.metchu.Fixtures
import com.example.metchu.data.network.BookmarkReply
import com.example.metchu.data.network.BookmarksReply
import com.example.metchu.data.network.HistoryReply
import com.example.metchu.data.network.RetrofitInstance
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The bookmark and history replies (backend/accounts), captured from a local server on the 2026-11-02 snapshot. */
class SavedContractJsonTest {

    private inline fun <reified T> parse(json: String): T = RetrofitInstance.gson.fromJson(json, T::class.java)

    @Test
    fun savedBookmark() {
        val bookmark = parse<BookmarkReply>(Fixtures.json("bookmark_saved")).bookmark
        assertEquals(6, bookmark.foodId)
        assertTrue(bookmark.displayName.startsWith("한입떡말이"))
        assertEquals("버거운버거", bookmark.restaurant)
        assertTrue(bookmark.createdAt!!.startsWith("2026-11-25T"))
    }

    @Test
    fun bookmarksNewestFirst() {
        val bookmarks = parse<BookmarksReply>(Fixtures.json("bookmarks")).bookmarks
        assertEquals(listOf(5, 6), bookmarks.map { it.foodId })
        assertEquals(bookmarks.map { it.createdAt!! }.sortedDescending(), bookmarks.map { it.createdAt!! })
        assertEquals(parse<BookmarkReply>(Fixtures.json("bookmark_saved")).bookmark, bookmarks[1])
    }

    @Test
    fun history() {
        val history = parse<HistoryReply>(Fixtures.json("history")).history
        assertEquals(listOf(6, 5), history.map { it.foodId })
        val entry = history.first()
        assertEquals("2026-11-02" to "LU", entry.date to entry.meal)
        assertEquals("버거운버거", entry.restaurant)
        assertTrue(entry.displayName.isNotBlank() && entry.createdAt.isNotBlank())
    }

    @Test
    fun aWholeDayEntryHasNoMeal() {
        val json = Fixtures.json("history").replaceFirst("\"meal\": \"LU\"", "\"meal\": null")
        assertNull(parse<HistoryReply>(json).history.first().meal)
    }
}
