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

/** The bookmark and history replies (backend/accounts), captured from a local server (client/README.md, Tests). */
class SavedContractJsonTest {

    private inline fun <reified T> parse(json: String): T = RetrofitInstance.gson.fromJson(json, T::class.java)

    @Test
    fun savedBookmark() {
        val bookmark = parse<BookmarkReply>(Fixtures.json("bookmark_saved")).bookmark
        assertEquals(1, bookmark.id)
        assertEquals("버거운버거", bookmark.restaurant)
        assertNull(bookmark.address)
        assertTrue(bookmark.createdAt!!.startsWith("2026-11-28T"))
    }

    @Test
    fun bookmarksNewestFirstWithTheAddressesKnown() {
        val bookmarks = parse<BookmarksReply>(Fixtures.json("bookmarks")).bookmarks
        assertEquals(listOf("홍콩반점 낙성대점", "버거운버거"), bookmarks.map { it.restaurant })
        assertEquals(listOf("서울특별시 관악구 남부순환로 1900", null), bookmarks.map { it.address })
        assertEquals(listOf(2, 1), bookmarks.map { it.id })
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
