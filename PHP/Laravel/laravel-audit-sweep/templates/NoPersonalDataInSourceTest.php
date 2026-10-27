<?php

namespace Tests\Feature;

use PHPUnit\Framework\TestCase;

/**
 * Fixtures are invented, and nothing in source points at a real person.
 *
 * Set OWNER to the owner's names and handles. The phone, ID and IBAN shapes
 * are Turkish (+90, TCKN, TR IBAN); adjust them for another country.
 */
class NoPersonalDataInSourceTest extends TestCase
{
    private const OWNER = '/firstname|lastname|handle/i';

    private const FIXTURES = ['tests', 'database/seeders', 'database/factories'];

    private const CODE = ['app', 'config', 'routes', 'database', 'tests', 'resources/js', 'resources/views', 'lang'];

    /**
     * @param  array<int, string>  $roots
     * @return iterable<string, array<int, string>>
     */
    private function lines(array $roots): iterable
    {
        $base = dirname(__DIR__, 2);

        foreach ($roots as $root) {
            $files = new \RecursiveIteratorIterator(new \RecursiveDirectoryIterator("$base/$root", \FilesystemIterator::SKIP_DOTS));

            foreach ($files as $file) {
                if (! preg_match('/\.(php|js|ts|vue|json)$/', $file->getFilename()) || $file->getRealPath() === __FILE__) {
                    continue;
                }

                yield substr($file->getPathname(), strlen($base) + 1) => file($file->getPathname(), FILE_IGNORE_NEW_LINES);
            }
        }
    }

    /**
     * @param  array<int, string>  $roots
     * @return array<int, string>
     */
    private function matching(array $roots, string $pattern, ?\Closure $offending = null): array
    {
        $found = [];

        foreach ($this->lines($roots) as $path => $lines) {
            foreach ($lines as $number => $line) {
                if (! preg_match_all($pattern, $line, $matches)) {
                    continue;
                }

                foreach ($matches[0] as $match) {
                    if ($offending === null || $offending($match)) {
                        $found[] = $path.':'.($number + 1).'  '.$match;
                    }
                }
            }
        }

        return $found;
    }

    public function test_fixture_addresses_are_on_a_domain_nobody_owns(): void
    {
        $found = $this->matching(self::FIXTURES, '/[\w.%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+/i', function (string $address) {
            $domain = strtolower(rtrim(substr($address, strpos($address, '@') + 1), '.'));

            return ! preg_match('/(^|\.)(example\.(com|org|net)|test|invalid|localhost)$|\.invalid\.[a-z0-9]+$/', $domain);
        });

        $this->assertSame([], $found, 'Use example.com, .test, or .invalid.<random>.');
    }

    public function test_fixture_phones_have_a_zeroed_subscriber(): void
    {
        $shapes = '/(?:\+90 ?|(?<![\d.])0)?\(?[2-5]\d{2}\)? ?\d{3} ?\d{2} ?\d{2}(?![\d.])/';

        $found = $this->matching(self::FIXTURES, $shapes, function (string $phone) {
            $digits = preg_replace('/\D/', '', $phone);

            // Bare ten digits with no prefix or spacing are ids and counts.
            if (! preg_match('/[ +(]|^0/', $phone)) {
                return false;
            }

            return substr(substr($digits, -10), 3, 5) !== '00000';
        });

        $this->assertSame([], $found, 'Write fixture numbers as 5XX 000 00 NN.');
    }

    public function test_no_national_id_iban_or_card_number(): void
    {
        $identity = $this->matching(self::CODE, '/(?<![\d.])[1-9]\d{10}(?![\d.])/', fn (string $number) => $this->isTurkishId($number));
        $iban = $this->matching(self::CODE, '/\bTR\d{2}(?: ?\d{4}){5} ?\d{2}\b/');
        $card = $this->matching(self::CODE, '/(?<!\d)[3-6](?:[ -]?\d){12,18}(?!\d)/', function (string $number) {
            $digits = preg_replace('/\D/', '', $number);

            return count(array_unique(str_split($digits))) > 2 && $this->passesLuhn($digits);
        });

        $this->assertSame([], [...$identity, ...$iban, ...$card]);
    }

    public function test_no_real_person_is_named(): void
    {
        $this->assertSame([], $this->matching(self::CODE, self::OWNER));
    }

    public function test_no_role_is_granted_to_a_literal_address(): void
    {
        $this->assertSame([], $this->matching(['app', 'database'], '/[\'"][^\'"@\s]+@[^\'"\s]+[\'"]\)[^;]*->assignRole/'));
    }

    private function isTurkishId(string $number): bool
    {
        $d = array_map('intval', str_split($number));

        if (count(array_unique($d)) === 1) {
            return false;
        }

        $tenth = ((($d[0] + $d[2] + $d[4] + $d[6] + $d[8]) * 7) - ($d[1] + $d[3] + $d[5] + $d[7])) % 10;

        return ($tenth + 10) % 10 === $d[9] && array_sum(array_slice($d, 0, 10)) % 10 === $d[10];
    }

    private function passesLuhn(string $digits): bool
    {
        $sum = 0;

        foreach (array_reverse(str_split($digits)) as $i => $digit) {
            $n = (int) $digit * ($i % 2 ? 2 : 1);
            $sum += $n > 9 ? $n - 9 : $n;
        }

        return $sum % 10 === 0;
    }
}
