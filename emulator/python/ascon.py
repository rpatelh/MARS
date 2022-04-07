#!/usr/bin/env python3

"""
Python3 implementation of Ascon v1.2, an authenticated cipher
http://ascon.iaik.tugraz.at/

Ported from python2
Added Hash()
Test vectors from KAT/AEAD_tvs added.
T. Brostrom
"""

debug = False
debugpermutation = False

# === Ascon encryption and decryption ===

def ascon_encrypt(key, nonce, associateddata, plaintext, variant="Ascon-128"): 
    """
    Ascon encryption.
    key: a bytes object of size 16 (for 128-bit security)
    nonce: a bytes object of size 16 (must not repeat for the same key!)
    associateddata: a bytes object of arbitrary length
    plaintext: a bytes object of arbitrary length
    variant: "Ascon-128" or "Ascon-128a" (specifies rate and number of rounds)
    returns a bytes object containing the ciphertext and tag
    """
    assert(len(key) == 16 and len(nonce) <= 16)
    S = [0, 0, 0, 0, 0]
    k = len(key) * 8   # bits
    a = 12   # rounds
    b = 6 if variant == "Ascon-128" else 8   # rounds
    rate = 8 if variant == "Ascon-128" else 16   # bytes

    ascon_initialize(S, k, rate, a, b, key, nonce)
    ascon_process_associated_data(S, b, rate, associateddata)
    ciphertext = ascon_process_plaintext(S, b, rate, plaintext)
    tag = ascon_finalize(S, rate, a, key)
    return ciphertext + tag


def ascon_decrypt(key, nonce, associateddata, ciphertext, variant="Ascon-128"):
    """
    Ascon decryption.
    key: a bytes object of size 16 (for 128-bit security)
    nonce: a bytes object of size 16 (must not repeat for the same key!)
    associateddata: a bytes object of arbitrary length
    ciphertext: a bytes object of arbitrary length (also contains tag)
    variant: "Ascon-128" or "Ascon-128a" (specifies rate and number of rounds)
    returns a bytes object containing the plaintext or None if verification fails
    """
    assert(len(key) == 16 and len(nonce) <= 16)
    assert(len(ciphertext) >= len(key))
    S = [0, 0, 0, 0, 0]
    k = len(key) * 8 # bits
    a = 12 # rounds
    b = 6 if variant == "Ascon-128" else 8  # rounds
    rate = 8 if variant == "Ascon-128" else 16 # bytes

    ascon_initialize(S, k, rate, a, b, key, nonce)
    ascon_process_associated_data(S, b, rate, associateddata)
    plaintext = ascon_process_ciphertext(S, b, rate, ciphertext[:-len(key)])
    tag = ascon_finalize(S, rate, a, key)
    if tag == ciphertext[-len(key):]:
        return plaintext
    else:
        return None


# === Ascon building blocks ===

def ascon_initialize(S, k, rate, a, b, key, nonce):
    """
    Ascon initialization phase. 
    S: Ascon state, a list of 5 64-bit integers
    k: key size in bits
    rate: block size in bytes (8 for Ascon-128, 16 for Ascon-128a)
    a: number of initialization/finalization rounds for permutation
    b: number of intermediate rounds for permutation
    key: a bytes object of size 16 (for 128-bit security)
    nonce: a bytes object of size 16
    returns nothing, updates S
    """
    zero_key_nonce = zero_bytes(32-len(key)-len(nonce)) + key + nonce
    zero_key = zero_bytes(16-len(key)) + key
    S[0] = bytes_to_int(to_bytes([k, rate * 8, a, b, 0, 0, 0, 0]))
    S[1] = bytes_to_int(zero_key_nonce[0:8])
    S[2] = bytes_to_int(zero_key_nonce[8:16])
    S[3] = bytes_to_int(zero_key_nonce[16:24])
    S[4] = bytes_to_int(zero_key_nonce[24:32])
    if debug: printstate(S, "initial value:")

    ascon_permutation(S, a)

    S[3] ^= bytes_to_int(zero_key[0:8])
    S[4] ^= bytes_to_int(zero_key[8:16])
    if debug: printstate(S, "initialization:")


def ascon_process_associated_data(S, b, rate, associateddata):
    """
    Ascon associated data processing phase. 
    S: Ascon state, a list of 5 64-bit integers
    b: number of intermediate rounds for permutation
    rate: block size in bytes (8 for Ascon-128, 16 for Ascon-128a)
    associateddata: a bytes object of arbitrary length
    returns nothing, updates S
    """
    if len(associateddata) > 0:
        a_zeros = rate - (len(associateddata) % rate) - 1
        a_padding = to_bytes([0x80] + [0 for i in range(a_zeros)])
        a_padded = associateddata + a_padding

        for block in range(0, len(a_padded), rate):
            S[0] ^= bytes_to_int(a_padded[block:block+8])
            if rate == 16:
                S[1] ^= bytes_to_int(a_padded[block+8:block+16])

            ascon_permutation(S, b)

    S[4] ^= 1
    if debug: printstate(S, "process associated data:")


def ascon_process_plaintext(S, b, rate, plaintext):
    """
    Ascon plaintext processing phase (during encryption). 
    S: Ascon state, a list of 5 64-bit integers
    b: number of intermediate rounds for permutation
    rate: block size in bytes (8 for Ascon-128, 16 for Ascon-128a)
    plaintext: a bytes object of arbitrary length
    returns the ciphertext (without tag), updates S
    """
    p_lastlen = len(plaintext) % rate
    p_padding = to_bytes([0x80] + (rate-p_lastlen-1)*[0x00])
    p_padded = plaintext + p_padding

    # first t-1 blocks
    ciphertext = to_bytes([])
    for block in range(0, len(p_padded) - rate, rate):
        if rate == 8:
            S[0] ^= bytes_to_int(p_padded[block:block+8])
            ciphertext += int_to_bytes(S[0], 8)
        elif rate == 16:
            S[0] ^= bytes_to_int(p_padded[block:block+8])
            S[1] ^= bytes_to_int(p_padded[block+8:block+16])
            ciphertext += (int_to_bytes(S[0], 8) + int_to_bytes(S[1], 8))

        ascon_permutation(S, b)

    # last block t
    block = len(p_padded) - rate
    if rate == 8:
        S[0] ^= bytes_to_int(p_padded[block:block+8])
        ciphertext += int_to_bytes(S[0], 8)[:p_lastlen]
    elif rate == 16:
        S[0] ^= bytes_to_int(p_padded[block:block+8])
        S[1] ^= bytes_to_int(p_padded[block+8:block+16])
        ciphertext += (int_to_bytes(S[0], 8)[:min(8,p_lastlen)] + int_to_bytes(S[1], 8)[:max(0,p_lastlen-8)])
    if debug: printstate(S, "process plaintext:")
    return ciphertext


def ascon_process_ciphertext(S, b, rate, ciphertext):
    """
    Ascon ciphertext processing phase (during decryption). 
    S: Ascon state, a list of 5 64-bit integers
    b: number of intermediate rounds for permutation
    rate: block size in bytes (8 for Ascon-128, 16 for Ascon-128a)
    ciphertext: a bytes object of arbitrary length
    returns the plaintext, updates S
    """
    c_lastlen = len(ciphertext) % rate
    c_padded = ciphertext + zero_bytes(rate - c_lastlen)

    # first t-1 blocks
    plaintext = to_bytes([])
    for block in range(0, len(c_padded) - rate, rate):
        if rate == 8:
            Ci = bytes_to_int(c_padded[block:block+8])
            plaintext += int_to_bytes(S[0] ^ Ci, 8)
            S[0] = Ci
        elif rate == 16:
            Ci = (bytes_to_int(c_padded[block:block+8]), bytes_to_int(c_padded[block+8:block+16]))
            plaintext += (int_to_bytes(S[0] ^ Ci[0], 8) + int_to_bytes(S[1] ^ Ci[1], 8))
            S[0] = Ci[0]
            S[1] = Ci[1]

        ascon_permutation(S, b)

    # last block t
    block = len(c_padded) - rate
    if rate == 8:
        c_padding1 = (0x80 << (rate-c_lastlen-1)*8)
        c_mask = (0xFFFFFFFFFFFFFFFF >> (c_lastlen*8))
        Ci = bytes_to_int(c_padded[block:block+8])
        plaintext += int_to_bytes(Ci ^ S[0], 8)[:c_lastlen]
        S[0] = Ci ^ (S[0] & c_mask) ^ c_padding1
    elif rate == 16:
        c_lastlen_word = c_lastlen % 8
        c_padding1 = (0x80 << (8-c_lastlen_word-1)*8)
        c_mask = (0xFFFFFFFFFFFFFFFF >> (c_lastlen_word*8))
        Ci = (bytes_to_int(c_padded[block:block+8]), bytes_to_int(c_padded[block+8:block+16]))
        plaintext += (int_to_bytes(S[0] ^ Ci[0], 8) + int_to_bytes(S[1] ^ Ci[1], 8))[:c_lastlen]
        if c_lastlen < 8:
            S[0] = Ci[0] ^ (S[0] & c_mask) ^ c_padding1
        else:
            S[0] = Ci[0]
            S[1] = Ci[1] ^ (S[1] & c_mask) ^ c_padding1
    if debug: printstate(S, "process ciphertext:")
    return plaintext


def ascon_finalize(S, rate, a, key):
    """
    Ascon finalization phase.
    S: Ascon state, a list of 5 64-bit integers
    rate: block size in bytes (8 for Ascon-128, 16 for Ascon-128a)
    a: number of initialization/finalization rounds for permutation
    key: a bytes object of size 16 (for 128-bit security)
    returns the tag, updates S
    """
    assert(len(key) == 16)
    S[rate//8+0] ^= bytes_to_int(key[0:8])
    S[rate//8+1] ^= bytes_to_int(key[8:16])

    ascon_permutation(S, a)

    S[3] ^= bytes_to_int(key[0:8])
    S[4] ^= bytes_to_int(key[8:16])
    tag = int_to_bytes(S[3], 8) + int_to_bytes(S[4], 8)
    if debug: printstate(S, "finalization:")
    return tag


def ascon_permutation(S, rounds=1):
    """
    Ascon core permutation for the sponge construction.
    S: Ascon state, a list of 5 64-bit integers
    rounds: number of rounds to perform
    returns nothing, updates S
    """
    assert(rounds <= 12)
    if debugpermutation: printwords(S, "permutation input:")
    for r in range(12-rounds, 12):
        # --- add round constants ---
        S[2] ^= (0xf0 - r*0x10 + r*0x1)
        if debugpermutation: printwords(S, "round constant addition:")
        # --- substitution layer ---
        S[0] ^= S[4]
        S[4] ^= S[3]
        S[2] ^= S[1]
        T = [(S[i] ^ 0xFFFFFFFFFFFFFFFF) & S[(i+1)%5] for i in range(5)]
        for i in range(5):
            S[i] ^= T[(i+1)%5]
        S[1] ^= S[0]
        S[0] ^= S[4]
        S[3] ^= S[2]
        S[2] ^= 0XFFFFFFFFFFFFFFFF
        if debugpermutation: printwords(S, "substitution layer:")
        # --- linear diffusion layer ---
        S[0] ^= rotr(S[0], 19) ^ rotr(S[0], 28)
        S[1] ^= rotr(S[1], 61) ^ rotr(S[1], 39)
        S[2] ^= rotr(S[2],  1) ^ rotr(S[2],  6)
        S[3] ^= rotr(S[3], 10) ^ rotr(S[3], 17)
        S[4] ^= rotr(S[4],  7) ^ rotr(S[4], 41)
        if debugpermutation: printwords(S, "linear diffusion layer:")


def ascon_hash(data):
    rate = 64 >> 3 # 64/8
    a = 12 # rounds
    # for the IV, see section 2.5.1 of
    # https://csrc.nist.gov/CSRC/media/Projects/Lightweight-Cryptography/documents/round-1/spec-doc/ascon-spec.pdf
    # 0 ∥ r ∥ a ∥ 0 ∥ h, where h is 32 bits, others are 8 bits
    # S = [ (((rate<<11) | a) << 40) | 256, 0, 0, 0, 0 ]
    S = [ 0x00400c0000000100, 0, 0, 0, 0 ] # set to IV
    if debug: printstate(S, "initial value:")
    ascon_permutation(S, a)
    if debug: printstate(S, "permuted value:")

    p_lastlen = len(data) % rate
    p_padding = to_bytes([0x80] + (rate-p_lastlen-1)*[0x00])
    p_padded = data + p_padding
    if debug: print ("padded =", bytes_to_hex(p_padded))

    for block in range(0, len(p_padded), rate):
        S[0] ^= bytes_to_int(p_padded[block:block+8])
        ascon_permutation(S, a)
        if debug: printstate(S, "process data:")

    outlen = 32 # 256-bit digest
    digest = int_to_bytes(S[0], 8)
    while (outlen > rate):
        ascon_permutation(S, a)
        digest += int_to_bytes(S[0], 8)
        outlen -= rate

    # print("message:", bytes_to_hex(data))
    # print(" digest:", bytes_to_hex(digest))
    # print()
    return digest


# === helper functions ===

def zero_bytes(n):
    return bytes(n)

def to_bytes(l): # where l is a list or bytearray or bytes
    return bytes(bytearray(l))

def bytes_to_int(bytes):
    return int.from_bytes(bytes, 'big')

def int_to_bytes(integer, nbytes):
    return int.to_bytes(integer, nbytes, 'big')

def rotr(val, r):
    return val >> r | (val & (1<<r)-1) << (64-r)
    # return ((val >> r) | (val << (64-r))) & (1<<64)-1
    # return ((val >> r) | (val << (64-r))) & ~(~0<<64)
    # return ((val >> r) ^ (val << (64-r))) % (1 << 64)

def bytes_to_hex(b):
    return b.hex()

def printstate(S, description=""):
    print(" " + description)
    print(" ".join(["{s:016x}".format(s=s) for s in S]))

def printwords(S, description=""):
    print(" " + description)
    print("\n".join(["  x{i}={s:016x}".format(**locals()) for i, s in enumerate(S)]))


# === some demo if called directly ===

if __name__ == "__main__":
    keysize = 16

    def test1(k, n, ad, pt):
        ct = ascon_encrypt(k, n, ad, pt)
        pt2 = ascon_decrypt(k, n, ad, ct)

        if pt2 == None: 
            print("verification failed!")
            
        data = [
                ("key", k), 
                ("nonce", n), 
                ("plaintext", pt), 
                ("assoc data", ad), 
                ("ciphertext", ct[:-len(k)]), 
                ("tag", ct[-len(k):]), 
                ("received", pt2), 
               ]
        maxlen = max([len(text) for (text, val) in data])
        for text, val in data:
            print("{text}:{align} 0x{val} ({length} bytes)".format(text=text, align=((maxlen - len(text)) * " "), val=bytes_to_hex(val), length=len(val)))
        print()
        
    test1(
        bytes.fromhex("F2D0BE2FEBF4FA4C949215715CCB5857"),      # KeyID = 1, see sdi.txt
        b"",
        b"",
        b"")
    test1(
        bytes.fromhex("F2D0BE2FEBF4FA4C949215715CCB5857"),      # KeyID = 1, see sdi.txt
        bytes.fromhex("294B4B3C9FDA8C80F9FE6421418218D9"),
        b"",
        b"")

    test1(
        bytes.fromhex("DD33F53C52E8C47CCED3D63BA1F492E1"),      # KeyID = 10, see sdi.txt
        bytes.fromhex("3AACB9EF698C57CC1B2FEE567314DAFA"),
        bytes.fromhex("2EDBFFA2543F7A67732EE32FB34B1D0749DFA478C602BA0F405AEB021ED225B5"),
        bytes.fromhex("35BD9967B255E1D67D7E761EB534CBD62EFC8217DDAEE15D79A7A70061931A5E"))

    msg=b""
    ascon_hash(msg)
    for i in range(0x29):
        msg += int_to_bytes(i,1)
        ascon_hash(msg)

    ascon_hash(b"UMBC")
