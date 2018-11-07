/*
    Document   : echo
    Created on : Sep 24, 2018, 15:15
    Author     : W1773ND
    Description:
        sms_character_counter Js
*/

$(document).ready(function(){
    var smsNormalCount = [' ', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h',
        'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
        'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V',
        'W', 'X', 'Y', 'Z', 'Ä', 'ä',  'à', 'Å', 'å', 'Æ', 'æ', 'ß', 'Ç', 'è', 'é', 'É', 'ì', 'Ö', 'ö', 'ò', 'Ø', 'ø',
        'Ñ', 'ñ', 'Ü', 'ü', 'ù', '#', '¤', '%', '&', '(', ')', '*', '+', ',', '–', '.', '/', ':', ';',' <', '>', '=', '§',
        '$', '!', '?', '£', '¿', '¡', '@', '¥', 'Δ', 'Φ', 'Γ', 'Λ', 'Ω', 'Π', 'Ψ', 'Σ', 'Θ', 'Ξ', '»', '‘'].join(''),
        smsDoubleCount = ['^', '|', '€', '}', '{', '[', '~', ']', '\\'].join(''),
        maxlength;

    $('.sms-text').keyup(function () {
        var count = countChars();
        countPages(count);
    });

    function countChars() {
        var text = $('.sms-text').val(),
            char,
            count = 0;
        for (var i = 0; i < text.length; i++) {
            char = text[i];
            if (maxlength >= 153) {
                if (smsDoubleCount.indexOf(char) !== -1)
                    count += 2;
                else
                    count += 1;

            } else {
                count +=1;
            }

        }
        return count;
    }

    function countPages(count) {
        var text = $('.sms-text').val(),
            char,
            pageCount,
            totalLength;
        maxlength = 160;
        for (var i = 0; i < text.length; i++) {
            char = text[i];
            if (smsDoubleCount.indexOf(char) === -1 && smsNormalCount.indexOf(char) === -1) {
                maxlength = 70;
            }
        }
        if (count > maxlength) {
            if (maxlength >= 153) {
                maxlength -= 7;
            }
            else {
                maxlength -= 4;
            }
        }
        pageCount = Math.ceil(count/maxlength);
        totalLength = maxlength * pageCount;
        if (totalLength !== 0) $('.sms-btn-send').removeClass('disabled');
        else $('.sms-btn-send').addClass('disabled');
        $('.sms-char-count').text(count + " / " + totalLength);
        $('.sms-page-count').text(pageCount);
    }
});