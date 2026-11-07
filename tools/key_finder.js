function stableHook() {
    try {
        var sqlcipher = Process.findModuleByName("sqlcipher.dll");
        if (!sqlcipher) return false;

        // Try to resolve both standard SQLCipher initialization functions
        var sqlite3_key = sqlcipher.findExportByName("sqlite3_key");
        var sqlite3_key_v2 = sqlcipher.findExportByName("sqlite3_key_v2");

        if (sqlite3_key) {
            Interceptor.attach(sqlite3_key, {
                onEnter: function(args) {
                    console.log("\n[!!!] sqlite3_key Intercepted [!!!]");
                    // Signature: int sqlite3_key(sqlite3 *db, const void *pKey, int nKey)
                    var pKey = args[1];
                    var nKey = args[2].toInt32();

                    parseKeyMaterial(pKey, nKey);
                }
            });
        }

        if (sqlite3_key_v2) {
            Interceptor.attach(sqlite3_key_v2, {
                onEnter: function(args) {
                    console.log("\n[!!!] sqlite3_key_v2 Intercepted [!!!]");
                    // Signature: int sqlite3_key_v2(sqlite3 *db, const char *zDbName, const void *pKey, int nKey)
                    var pKey = args[2];
                    var nKey = args[3].toInt32();

                    parseKeyMaterial(pKey, nKey);
                }
            });
        }

        if (!sqlite3_key && !sqlite3_key_v2) {
            console.log("[-] Neither sqlite3_key nor sqlite3_key_v2 are explicitly exported by this DLL.");
            return false;
        }

        console.log("[+] Key Sniffer engaged. Monitoring cryptographic entries...");
        return true;
    } catch (e) {
        return false;
    }
}

// Helper function to safely read and display key data formats
function parseKeyMaterial(pKey, nKey) {
    if (pKey.isNull() || nKey <= 0 || nKey > 256) {
        console.log("[-] Key pointer invalid or length out of bounds (" + nKey + " bytes).");
        return;
    }

    console.log("[+] Key material detected! Length: " + nKey + " bytes");

    try {
        // Attempt 1: Read as a standard UTF-8 string (if passphrase text)
        var utf8Str = pKey.readUtf8String(nKey);
        if (utf8Str && /^[a-zA-Z0-9_\-\+\=\/]{4,}$/.test(utf8Str)) {
            console.log(" -> Text/Passphrase Format: " + utf8Str);
        }
    } catch (strErr) {}

    try {
        // Attempt 2: Always dump as Raw Hex (in case it's a pre-computed SHA256 / AES key block)
        var rawBytes = pKey.readByteArray(nKey);
        console.log(" -> Raw Hex Format:\n" + hexdump(rawBytes, { header: false, answers: false }));
    } catch (hexErr) {
        console.log(" -> Failed to extract raw buffer memory layout.");
    }
}

var hookTimer = setInterval(function() {
    try {
        if (stableHook()) clearInterval(hookTimer);
    } catch(err) {}
}, 100);