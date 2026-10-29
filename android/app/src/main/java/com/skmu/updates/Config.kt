package com.skmu.updates

object Config {
    // Testing (Termux server isi phone par): "http://127.0.0.1:5000"
    // Play Store / sabke liye: apna online server, jaise "https://skmu-updates.example.com"
    // (aakhir me "/" mat lagana)
    const val BASE_URL = "http://127.0.0.1:5000"

    // Naye update ki jaanch kitne minute me ho (Android ke hisab se kam se kam 15)
    const val POLL_MINUTES = 15L
}
