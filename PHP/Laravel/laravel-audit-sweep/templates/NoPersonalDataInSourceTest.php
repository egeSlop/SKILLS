<?php

namespace Tests\Feature;

use PHPUnit\Framework\TestCase;

/**
 * Fixtures are invented, and nothing in source points at a real person.
 *
 * Set OWNER to the owner's names and handles, and list the national ID shapes of
 * the countries the project serves in nationalIds(). Phones, IBANs and card
 * numbers are checked for every country.
 */
class NoPersonalDataInSourceTest extends TestCase
{
    private const OWNER = '/firstname|lastname|handle/i';

    private const FIXTURES = ['tests', 'database/seeders', 'database/factories'];

    private const CODE = ['app', 'config', 'routes', 'database', 'tests', 'resources/js', 'resources/ts', 'resources/views', 'lang'];

    /**
     * @param  array<int, string>  $roots
     * @return iterable<string, array<int, string>>
     */
    private function lines(array $roots): iterable
    {
        $base = dirname(__DIR__, 2);

        foreach ($roots as $root) {
            if (! is_dir("$base/$root")) {
                continue;
            }

            $files = new \RecursiveIteratorIterator(new \RecursiveDirectoryIterator("$base/$root", \FilesystemIterator::SKIP_DOTS));

            foreach ($files as $file) {
                if (! preg_match('/\.(php|js|ts|jsx|tsx|vue|svelte|json)$/', $file->getFilename()) || $file->getRealPath() === __FILE__) {
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
        $shapes = '/(?<![\w.+])(?:\+\d{9,14}|0\d{9,11}|(?:\+\d{1,3}[ -]?)?(?:\(?\d{2,5}\)?[ -]){1,4}\d{2,5})(?![\w.])/';

        $found = $this->matching(self::FIXTURES, $shapes, function (string $phone) {
            $phone = trim($phone);
            $digits = preg_replace('/\D/', '', $phone);

            // Bare digit runs with no prefix or spacing are ids and counts.
            if (strlen($digits) < 9 || strlen($digits) > 15 || ! preg_match('/[ (-]|^[+0]/', $phone)) {
                return false;
            }

            return ! str_contains(substr($digits, -8), '0000') && ! preg_match('/555[ -]?01\d\d$/', $phone);
        });

        $this->assertSame([], $found, 'Give fixture numbers a run of zeros in the subscriber part: +CC NNN 0000 NN.');
    }

    public function test_no_national_id_iban_or_card_number(): void
    {
        $identity = [];

        foreach ($this->nationalIds() as $pattern => $isValid) {
            $identity = [...$identity, ...$this->matching(self::CODE, $pattern, $isValid)];
        }

        $iban = $this->matching(self::CODE, '/\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b/', fn (string $iban) => $this->passesMod97($iban));
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

    /**
     * The national ID shapes of the countries the project serves, each with its
     * checksum: an invented number that passes the checksum is somebody's.
     * For example a Turkish TCKN: '/(?<![\d.])[1-9]\d{10}(?![\d.])/' => its checksum.
     *
     * @return array<string, \Closure(string): bool>
     */
    private function nationalIds(): array
    {
        return [];
    }

    private function passesMod97(string $iban): bool
    {
        $iban = str_replace(' ', '', $iban);
        $remainder = 0;

        foreach (str_split(substr($iban, 4).substr($iban, 0, 4)) as $character) {
            $value = ctype_alpha($character) ? (string) (ord($character) - 55) : $character;

            foreach (str_split($value) as $digit) {
                $remainder = ($remainder * 10 + (int) $digit) % 97;
            }
        }

        return $remainder === 1;
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
